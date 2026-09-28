/**
 * "Solve it here" on the desktop (the owner's decision of 2026-09-28,
 * CLAUDE.md "A captcha can be handed to the owner's phone"; JARVIS-API.md
 * section 60.8; backend/jarvis_handoff.py).
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
  return { kind, id, reason, site: text(o.site) || "The website", active: text(o.active) };
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
