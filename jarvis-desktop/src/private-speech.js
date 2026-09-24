/**
 * May the answer to a question asked BY VOICE be read aloud? The owner's
 * rule (docs/JARVIS-API.md section 16, "What the apps must do about
 * private answers"), as one function with no page in it
 * (tests/private-speech.mjs).
 *
 * With "private answers stay on screen" (the default), an answer drawn
 * from email, the calendar or notes is shown, and not read aloud, unless
 * the question was typed. An answer that uses what Jarvis remembers is read
 * aloud by default (the owner's choice, 2026-09-24: `memory_aloud`), and
 * kept on screen too when the owner chooses "keep on screen". So for a voice question
 * whose utterance reply said `private_aloud: false` - or did not say at
 * all, which is what an older PC sends - the answer is read aloud only
 * when nothing says it is private:
 *
 *   - `question_private` is not true (the words asked about something
 *     private: the router's private-topic list, plus notes and memory);
 *   - the chat reply's `X-Jarvis-Route` has no `gate: "private"`;
 *   - only when `memory_aloud` is not true: it has no `injected_facts`
 *     above 0 (remembered facts went in);
 *   - no tool ran while it was being written - and that is only known
 *     while the event stream is live, so an unknown counts as "a tool may
 *     have run". Exactly the phone's rule (jarvis-client
 *     voice/PrivateAloud.kt). A tool that ran is read from the `step`
 *     event (docs/JARVIS-API.md section 2): `phase` `tool_started` or
 *     `tool_finished`, counted from the moment the question was sent to
 *     the moment each sentence is spoken (`createToolWatch`). The chat
 *     stream's `: jarvis-status working` / `approval` still counts too, but
 *     it is not enough on its own: the PC sends it only after 1.5 seconds
 *     (jarvis_agent.STATUS_DELAY_SECONDS), so a quick `calendar_read` or
 *     `email_read` says nothing there. The `step` event has no such delay.
 *
 * Otherwise Jarvis says one fixed line instead, `PRIVATE_LINE`, once.
 * `private_aloud: true` (the owner chose "voice check is enough", and the
 * very strict check passed) reads everything else aloud as before.
 *
 * One step comes before all of that (the owner's decision 13, 2026-09-24:
 * sensitive saved facts stay on screen): an answer that used a SENSITIVE
 * saved fact - health, money, passwords, other people - is kept on screen
 * unless the utterance reply said `sensitive_aloud: true` (the owner chose
 * "Read aloud" under "Answers that use sensitive saved facts" and a real
 * voice check passed). That holds even with `private_aloud` or
 * `memory_aloud` true. The route line says how many of the facts that went
 * in were sensitive (`injected_sensitive`); a PC that does not say, while
 * `injected_facts` is above 0, is read as "they may all be sensitive".
 *
 * @module private-speech
 */

/** What Jarvis says instead of reading a private answer aloud. */
export const PRIVATE_LINE = "It's on your screen.";

/** The `: jarvis-status` words that mean a tool ran (or waited on a card). */
export const TOOL_WORDS = Object.freeze(["working", "approval"]);

/**
 * The privacy facts of one voice question, from the utterance reply
 * (`HeardReply`, camelCased by voice.rs): `{privateAloud, questionPrivate,
 * memoryAloud, sensitiveAloud}`. Anything missing reads as the refusing
 * answer for `privateAloud`, `memoryAloud` and `sensitiveAloud` (an older
 * PC), and as "not said" for `questionPrivate`.
 */
export function privacyFromHeard(heard) {
  const h = heard && typeof heard === "object" ? heard : {};
  return {
    privateAloud: h.privateAloud === true,
    questionPrivate: h.questionPrivate === true,
    memoryAloud: h.memoryAloud === true,
    sensitiveAloud: h.sensitiveAloud === true,
  };
}

/**
 * Did a sensitive saved fact go into this answer? The route line's
 * `injected_sensitive` above 0 - or, from a PC that does not send it,
 * any `injected_facts` at all (fail closed: they may all be sensitive).
 */
export function usedSensitiveFact(route) {
  const r = route && typeof route === "object" ? route : {};
  const facts = Number(r.injected_facts);
  const hasSensitive = Object.prototype.hasOwnProperty.call(r, "injected_sensitive");
  const sensitive = Number(r.injected_sensitive);
  if (hasSensitive && Number.isFinite(sensitive)) return sensitive > 0;
  return Number.isFinite(facts) && facts > 0;
}

/** Does a `step` event's `data` say a tool ran (started, or finished)?
 *  A refused tool did not run. The phone's `PrivateAloud.isToolRun`. */
export function isToolRun(data) {
  const phase = data && typeof data === "object" ? data.phase : undefined;
  return phase === "tool_started" || phase === "tool_finished";
}

/**
 * What this window knows about tools, as counters: `runs` (`step` events
 * that said a tool ran), `drops` (times the event stream stopped being
 * live, or fell off the back of the server's ring) and `live` (connected
 * and not stale now). Two snapshots - one when the question was sent, one
 * when a sentence is about to be spoken - say whether a tool ran in
 * between, and whether this window could have heard of it. The phone's
 * `PrivateAloud.Watch`, kept the same way.
 */
export function createToolWatch() {
  let runs = 0;
  let drops = 0;
  let live = false;
  return {
    /** A `jarvis-link` state (`{connected, stale}`). */
    link(state) {
      const now = Boolean(state && state.connected === true && state.stale === false);
      if (live && !now) drops += 1;
      live = now;
    },
    /** A fanned-out bus frame, `{kind, id, data}`. */
    event(frame) {
      if (frame && frame.kind === "step" && isToolRun(frame.data)) runs += 1;
    },
    /** `jarvis-resync`: events were missed. */
    resync() {
      drops += 1;
    },
    snapshot() {
      return { runs, drops, live };
    },
  };
}

/** A tool ran between two snapshots. */
export function toolRanBetween(start, now) {
  if (!start || !now) return false;
  return now.runs !== start.runs;
}

/** The stream was live at both snapshots and did not drop in between, so a
 *  tool that ran would have been heard of. A missing snapshot: not known. */
export function toolsKnownBetween(start, now) {
  if (!start || !now) return false;
  return start.live === true && now.live === true && start.drops === now.drops;
}

/**
 * May this answer be read aloud? `ctx`: `{privateAloud, questionPrivate,
 * memoryAloud, sensitiveAloud}` from the question, `route` (the route
 * line's object: `gate`, `injected_facts`, `injected_sensitive`),
 * `toolRan`, and `toolsKnown` (the event stream was live the whole time;
 * anything but `true` counts as "a tool may have run", as on the phone).
 */
export function mayReadAloud(ctx) {
  const c = ctx && typeof ctx === "object" ? ctx : {};
  // Decision 13, first: a sensitive saved fact stays on screen unless the
  // owner chose to hear those answers - whatever else says "aloud".
  if (usedSensitiveFact(c.route) && c.sensitiveAloud !== true) return false;
  if (c.privateAloud === true) return true;
  if (c.questionPrivate === true) return false;
  const route = c.route && typeof c.route === "object" ? c.route : {};
  if (String(route.gate || "").trim().toLowerCase() === "private") return false;
  const facts = Number(route.injected_facts);
  if (Number.isFinite(facts) && facts > 0 && c.memoryAloud !== true) return false;
  if (c.toolRan === true) return false;
  if (c.toolsKnown !== true) return false;
  return true;
}
