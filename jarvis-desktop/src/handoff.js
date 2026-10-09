/**
 * "Solve it here" on the desktop (the owner's decision of 2026-09-28,
 * CLAUDE.md "A captcha can be handed to the owner's phone"; JARVIS-API.md
 * section 87.8; backend/jarvis_handoff.py).
 *
 * When a chatbot conversation or a customer-support chat pauses at a
 * captcha, a sign-in page or an "unusual activity" page, GET
 * /api/chatbot/status carries `handoff`: which site and why - never a
 * picture, never a word from the page. The PHONE offers "Solve it here" (a
 * live picture of that one browser window); on the PC the window is right
 * there, so the Brain's Work tab shows the same alert, in the same words,
 * pointing at the window - and says the phone can do it too. Nothing here
 * pictures, taps or types anything: the desktop never calls the hand-off's
 * picture or input routes (ARCHITECTURE.md section 8, "One-sided on
 * purpose").
 */

/** The PC's own sentences (jarvis_handoff.WORDS), word for word. */
export const WORDS = {
  title: "Solve it here",
  alert_title: "{site} needs you",
  alert_locked: "A website Jarvis is using needs you",
  alert_text: "Jarvis paused: {reason}. Solve it here, or in the window on the PC.",
  reason_captcha: "a captcha (a \"prove you are a person\" check)",
  reason_login: "a sign-in page",
  reason_unusual: "an \"unusual activity\" page",
  here_button: "Solve it here",
  pc_button: "Solve it on the PC instead",
  detail: "A live picture of that one browser window on your PC, sent only to this phone and "
    + "never saved. Your taps and typing go to that window only, and only while Jarvis is "
    + "paused there. Jarvis never solves it for you.",
  may_refuse: "Some captchas refuse taps passed on from a phone this way. If it keeps saying "
    + "no, solve it on the PC instead.",
  then_resume: "When it is done, press Resume. Resume asks with a card, as always.",
  type_label: "Type into the page",
  type_send: "Type it",
  keys_label: "Keys",
  scroll_up: "Scroll up",
  scroll_down: "Scroll down",
  end: "End",
  held_stale: "The link to your PC is catching up, so your taps and typing are held until it "
    + "is back.",
  locked: "Unlock Jarvis to see the page.",
  waiting: "Getting the picture...",
  pc_title: "{site} needs you on this PC",
  pc_text: "Jarvis paused: {reason}. Deal with it in the browser window, then press Resume. "
    + "Your phone can do it too (Solve it here).",
  new_window: "If the site opens a new window or tab, finish there on the PC - only the first "
    + "window is passed on.",
};

const REASONS = new Set(["captcha", "login", "unusual"]);
const KINDS = new Set(["chatbot", "support"]);

/**
 * The PC's own line for a window Jarvis is stuck on (jarvis_handoff.STUCK,
 * added 2026-10-08 with the "Stop early" setting): shown when the hand-off
 * ended the "Stop early" way, naming the site and the reason, so the owner
 * knows exactly which browser window on the PC to solve it in. Both apps show
 * it word for word (tools/gen_handoff_cases.py carries it).
 */
export const STUCK = {
  title: "{site} is waiting on this PC",
  text: "Jarvis is stuck on {reason} in that window, so the hand-off to your phone has ended. "
    + "Solve it in the browser window on this PC, then press Resume. Your phone can start it "
    + "again (Solve it here) if you need it.",
};

/** That line for one site and reason, exactly as the PC writes it. */
export function stuckLine(site, reason) {
  return {
    title: STUCK.title.replace("{site}", site),
    text: STUCK.text.replace("{reason}", reasonWords(reason)),
  };
}

const text = (v) => (typeof v === "string" ? v : "");

/**
 * The `handoff` field as a view, or null when nothing waits for the owner
 * (or the PC is older and sends none).
 */
export function readHandoff(o) {
  if (!o || typeof o !== "object" || o.available !== true) return null;
  const kind = text(o.kind);
  const reason = text(o.reason);
  const id = text(o.id);
  if (!KINDS.has(kind) || !REASONS.has(reason) || !id) return null;
  // `stuck` (the owner's setting of 2026-10-08): the PC's own two fixed
  // sentences for the window it is stuck on, or null. Two strings only -
  // never a page title, never a word the site said.
  const s = o.stuck && typeof o.stuck === "object" ? o.stuck : null;
  const stuck = s && text(s.title) && text(s.text)
    ? { title: text(s.title), text: text(s.text) }
    : null;
  return { kind, id, reason, site: text(o.site) || "The website", active: text(o.active), stuck };
}

/** What the reason is called ("a captcha (...)"). */
export function reasonWords(reason) {
  return WORDS[`reason_${reason}`] || WORDS.reason_captcha;
}

/**
 * The desktop's alert for [h] on the session with [kind] and [id]: {title,
 * text} - or null when [h] is about another session. The PC's window is
 * right there: the words point at it.
 */
export function pcLine(h, kind, id) {
  if (!h || h.kind !== kind || h.id !== id) return null;
  return {
    title: WORDS.pc_title.replace("{site}", h.site),
    text: WORDS.pc_text.replace("{reason}", reasonWords(h.reason)),
  };
}

/**
 * The PC's own line for a window Jarvis is stuck on, for the session with
 * [kind] and [id] - or null. Set on `handoff.stuck` (the PC's `_stuck_now`)
 * only when the hand-off ended the "Stop early" way while that page is still
 * paused: the offer is gone and the owner is told exactly which window to
 * solve the puzzle in, on this PC. Same fixed words as the phone's screen.
 */
export function stuckPcLine(h, kind, id) {
  if (!h || h.kind !== kind || h.id !== id || !h.stuck) return null;
  return { title: text(h.stuck.title), text: text(h.stuck.text) };
}
