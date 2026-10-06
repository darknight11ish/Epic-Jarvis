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
 *   - no PRIVATE tool ran while it was being written - and that is only
 *     known while the event stream is live, so an unknown counts as "a
 *     private tool may have run". Exactly the phone's rule (jarvis-client
 *     voice/PrivateAloud.kt). A tool that ran is read from the `step`
 *     event (docs/JARVIS-API.md section 2): `phase` `tool_started` or
 *     `tool_finished`, counted from the moment the question was sent to
 *     the moment each sentence is spoken (`createToolWatch`). A tool is
 *     private unless its name is on `READ_ALOUD_TOOLS` - web search and
 *     home status (the owner's decision of 2026-09-27; weather is read
 *     from home status). Email, calendar, notes, files, memory, a step
 *     with no name, "unknown" and any tool added later stay private. The
 *     chat stream's `: jarvis-status working` / `approval` carries no
 *     name, so it counts as private too - unless the `step` events since
 *     the question show tools ran and every one was on the list (the PC
 *     sends that status 1.5 s after the tool's `step` event, so by then the
 *     name is known; `onlyReadAloudToolsBetween`). The status is not
 *     enough on its own: a quick `calendar_read` says nothing there. The
 *     table both apps are held to: tests/fixtures/private-aloud-cases.json
 *     (tools/gen_private_aloud_cases.py).
 *
 * Otherwise Jarvis says one fixed line instead, `PRIVATE_LINE`, once.
 * `private_aloud: true` (the owner chose "voice check is enough", and the
 * very strict check passed) reads everything else aloud as before.
 *
 * One step comes before all of that (the owner's decision 13, 2026-09-24:
 * sensitive saved facts stay on screen): an answer that used a SENSITIVE
 * saved fact - health, money, passwords, other people's private details - is kept on screen
 * unless the utterance reply said `sensitive_aloud: true` (the owner chose
 * "Read aloud" under "Answers that use sensitive saved facts" and a real
 * voice check passed). That holds even with `private_aloud` or
 * `memory_aloud` true. The route line says how many of the facts that went
 * in were sensitive (`injected_sensitive`); a PC that does not say, while
 * `injected_facts` is above 0, is read as "they may all be sensitive".
 *
 * Right after it, the screen (the owner's decision of 2026-09-28): an
 * answer about the screen (`read_screen` ran) is kept on screen unless the
 * utterance reply said `screen_aloud: true`. The PC says true for the talk
 * button, and for "Hey Jarvis" under "Same as the talk button"; under "Only
 * trust the talk button", only when the owner turned on "Answers about your
 * screen after "Hey Jarvis"" (voice setting `hands_free_screen`). Missing
 * (an older PC) counts as false. Nothing after it can let such an answer
 * through - not even `private_aloud`.
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
 * memoryAloud, sensitiveAloud, screenAloud}`. Anything missing reads as the
 * refusing answer for `privateAloud`, `memoryAloud`, `sensitiveAloud` and
 * `screenAloud` (an older PC), and as "not said" for `questionPrivate`.
 */
export function privacyFromHeard(heard) {
  const h = heard && typeof heard === "object" ? heard : {};
  return {
    privateAloud: h.privateAloud === true,
    questionPrivate: h.questionPrivate === true,
    memoryAloud: h.memoryAloud === true,
    sensitiveAloud: h.sensitiveAloud === true,
    screenAloud: h.screenAloud === true,
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
 * The only tools whose answers may be read aloud to a voice question (the
 * owner's decision of 2026-09-27: web search, weather and home status -
 * weather is read with `home_read`, or answered with no tool at all) - and
 * `read_screen`, an answer about the screen (the owner's answer of
 * 2026-09-28; a read the PC records, not a model tool) - and `read_camera`,
 * an answer about what the phone's camera sees in Jarvis Live (the owner's
 * answer of 2026-09-28; off until the 12 GB card passes the photo test) -
 * and `read_web_page`, one page the owner handed over (the owner's request of
 * 2026-10-05, "post a webpage into jarvis and it can read the content out
 * loud"; `jarvis_readpage.ACTION`, served by `jarvis_readpage.run`). It sits
 * beside `web_search` rather than beside email, calendar, notes or memory:
 * both are the public web the owner asked for, and the page's address is
 * shown on a card before anything is fetched. Every earlier rule still comes
 * first - a sensitive saved fact, a private question, the router's private
 * gate, a forgotten event stream. It is one name here, and
 * tools/gen_private_aloud_cases.py generates the table both apps are held to.
 * Exact names, as the `step` event carries them. The phone's
 * `PrivateAloud.READ_ALOUD_TOOLS`.
 */
export const READ_ALOUD_TOOLS = Object.freeze(["home_read", "read_camera", "read_screen", "web_search",
  "read_web_page"]);

/** A tool ran, and its answer stays on screen: its name is not on
 *  `READ_ALOUD_TOOLS`, or it has none. The phone's `isPrivateToolRun`. */
export function isPrivateToolRun(data) {
  if (!isToolRun(data)) return false;
  const tool = data.tool;
  return typeof tool !== "string" || !READ_ALOUD_TOOLS.includes(tool);
}

/** The read an answer about the screen records (jarvis_screen.SCREEN_TOOL). */
export const SCREEN_READ = "read_screen";

/** The read an answer about the camera records (jarvis_live.CAMERA_TOOL). */
export const CAMERA_READ = "read_camera";

/** A `step` event says the screen - or, in Jarvis Live, the camera - was
 *  read: a tool run named exactly `read_screen` or `read_camera`. Both keep
 *  to the same rule (the owner's answer of 2026-09-28: camera answers are
 *  read aloud like screen answers). The phone's `PrivateAloud.isScreenRead`. */
export function isScreenRead(data) {
  return isToolRun(data) && (data.tool === SCREEN_READ || data.tool === CAMERA_READ);
}

/**
 * What this window knows about tools, as counters: `runs` (`step` events
 * that said a tool ran), `privateRuns` (those whose tool is not on
 * `READ_ALOUD_TOOLS`), `screenRuns` (those that were the screen being read,
 * `read_screen`), `drops` (times the event stream stopped being
 * live, or fell off the back of the server's ring) and `live` (connected
 * and not stale now). Two snapshots - one when the question was sent, one
 * when a sentence is about to be spoken - say whether a tool ran in
 * between, and whether this window could have heard of it. The phone's
 * `PrivateAloud.Watch`, kept the same way.
 */
export function createToolWatch() {
  let runs = 0;
  let privateRuns = 0;
  let screenRuns = 0;
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
      if (frame && frame.kind === "step" && isToolRun(frame.data)) {
        runs += 1;
        if (isPrivateToolRun(frame.data)) privateRuns += 1;
        if (isScreenRead(frame.data)) screenRuns += 1;
      }
    },
    /** `jarvis-resync`: events were missed. */
    resync() {
      drops += 1;
    },
    snapshot() {
      return { runs, privateRuns, screenRuns, drops, live };
    },
  };
}

/** The screen was read between two snapshots. A snapshot without
 *  `screenRuns` (not one this module made) counts every tool that ran as
 *  possibly the screen. The phone's `PrivateAloud.screenRead`. */
export function screenReadBetween(start, now) {
  if (!start || !now) return false;
  if (Number.isInteger(start.screenRuns) && Number.isInteger(now.screenRuns)) {
    return now.screenRuns !== start.screenRuns;
  }
  return now.runs !== start.runs;
}

/** A PRIVATE tool ran between two snapshots - one not on
 *  `READ_ALOUD_TOOLS`. A snapshot without `privateRuns` (not one this
 *  module made) counts every tool that ran as private. */
export function toolRanBetween(start, now) {
  if (!start || !now) return false;
  if (Number.isInteger(start.privateRuns) && Number.isInteger(now.privateRuns)) {
    return now.privateRuns !== start.privateRuns;
  }
  return now.runs !== start.runs;
}

/** Tools ran between two snapshots, and every one was on
 *  `READ_ALOUD_TOOLS`. What lets a nameless `: jarvis-status working` pass:
 *  the `step` events already said which tools those were. */
export function onlyReadAloudToolsBetween(start, now) {
  if (!start || !now) return false;
  if (!Number.isInteger(start.privateRuns) || !Number.isInteger(now.privateRuns)) return false;
  return now.runs !== start.runs && now.privateRuns === start.privateRuns;
}

/** The stream was live at both snapshots and did not drop in between, so a
 *  tool that ran would have been heard of. A missing snapshot: not known. */
export function toolsKnownBetween(start, now) {
  if (!start || !now) return false;
  return start.live === true && now.live === true && start.drops === now.drops;
}

/**
 * May this answer be read aloud? `ctx`: `{privateAloud, questionPrivate,
 * memoryAloud, sensitiveAloud, screenAloud}` from the question, `route` (the route
 * line's object: `gate`, `injected_facts`, `injected_sensitive`),
 * `toolRan` (a PRIVATE tool ran - `toolRanBetween`), `screenRead` (the
 * screen was read - `screenReadBetween`), and `toolsKnown` (the event stream was live the whole time;
 * anything but `true` counts as "a tool may have run", as on the phone).
 */
export function mayReadAloud(ctx) {
  const c = ctx && typeof ctx === "object" ? ctx : {};
  // Decision 13, first: a sensitive saved fact stays on screen unless the
  // owner chose to hear those answers - whatever else says "aloud".
  if (usedSensitiveFact(c.route) && c.sensitiveAloud !== true) return false;
  // Then the screen (the owner's decision of 2026-09-28): an answer about
  // the screen stays on screen unless the PC said `screen_aloud` for this
  // clip - false for "Hey Jarvis" under "Only trust the talk button" unless
  // the owner allowed it. Before `privateAloud`, so nothing lets it through.
  if (c.screenRead === true && c.screenAloud !== true) return false;
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
