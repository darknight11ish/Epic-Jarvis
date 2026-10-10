/**
 * The rules of Settings -> "When a captcha stops Jarvis" (the owner's own
 * decision of 2026-10-09, his words: "1 by default with the option for 2 in
 * the settings of Jarvis"; backend/jarvis_handoff_front.py;
 * docs/CAPTCHA-HANDOFF-DESIGN.md). Pure: no page, no Tauri, so
 * tests/handoff-front.mjs can run it.
 *
 * When a captcha or a sign-in page blocks the browser window Jarvis is
 * driving, this setting is what happens to that window on the PC:
 *
 *  - "Leave it where it is" (the DEFAULT, and the narrower one): the window is
 *    not touched - it keeps its size, its place and whatever is in front of
 *    it - and the PC says plainly which window Jarvis is stuck on
 *    (jarvis_handoff.STUCK), so the owner solves it there when they are ready;
 *  - "Bring it to the front": that one window is raised and activated the
 *    moment Jarvis is stuck, so it is in front and ready to type into. It
 *    takes the owner's screen and keyboard away from whatever they were doing,
 *    so choosing it is ONE approval card on the PC with Windows Hello. Going
 *    back is instant.
 *
 * Every sentence is the PC's own (`WORDS` in backend/jarvis_handoff_front.py):
 * tools/gen_handoff_cases.py carries them into both apps' contract file, and
 * tests/handoff-front.mjs holds this table to it, so the phone
 * (net/HandoffFront.kt) says exactly the same.
 *
 * @module handoff-front-rules
 */

export const HANDOFF_FRONT = Object.freeze({
  title: "When a captcha stops Jarvis",
  detail:
    "When Jarvis is stuck on a captcha or a sign-in page, it can leave that browser window exactly where it is - or bring it to the front so you can type into it. Either way the PC says which window is stuck.",
  leaveInPlace: "Leave it where it is",
  leaveInPlaceDetail:
    "The window is not touched: it keeps its size, its place and whatever is in front of it. The PC says which window Jarvis is stuck on, and you solve it there when you are ready.",
  bringToFront: "Bring it to the front",
  bringToFrontDetail:
    "That one window is raised and activated the moment Jarvis is stuck, so it is in front and ready to type into. It takes your screen and your keyboard away from whatever you were doing, so turning this on asks for your approval.",
  opensWindowsHello:
    "Turning \"Bring it to the front\" on asks for your approval on the PC.",
  waiting:
    "Waiting for your approval. The window stays where it is until you approve the card.",
  offNow: "Done. The window stays where it is again.",
  damaged:
    "the captcha window setting is damaged, so the window stays where it is. Choose \"Bring it to the front\" again to rewrite it",
  unread: "Could not read this setting.",
  waitingLink: "Waiting for the connection to your PC.",
  asking: "Asking your PC…",
});

/** The two values, in the PC's order, and the default (the narrower one). */
export const FRONT_MODES = Object.freeze(["leave_in_place", "bring_to_front"]);
export const DEFAULT_FRONT = "leave_in_place";
/** The one that raises the window, and so needs the card. */
export const BRING_TO_FRONT = "bring_to_front";

/** What each choice is called on the screen. */
export const FRONT_LABELS = Object.freeze({
  leave_in_place: HANDOFF_FRONT.leaveInPlace,
  bring_to_front: HANDOFF_FRONT.bringToFront,
});

/** The one line that says what each choice does. */
export const FRONT_HELP = Object.freeze({
  leave_in_place: HANDOFF_FRONT.leaveInPlaceDetail,
  bring_to_front: HANDOFF_FRONT.bringToFrontDetail,
});

/** A trimmed string, or "". */
export function words(x) {
  return typeof x === "string" ? x.trim() : "";
}

/** A real JSON true only - the string "true" is not one. */
function flag(x) {
  return x === true;
}

/**
 * What Settings shows for one GET /api/chatbot/handoff_front answer. The
 * reference is `view()` in backend/jarvis_handoff_front.py.
 * -> {available, mode, waiting, why, line, lastWords}
 */
export function frontView(out) {
  const o = out && typeof out === "object" && !Array.isArray(out) ? out : {};
  const mode = FRONT_MODES.includes(o.mode) ? o.mode : "";
  if (!mode) {
    return {
      available: false,
      mode: DEFAULT_FRONT,
      waiting: false,
      why: "",
      line: HANDOFF_FRONT.unread,
      lastWords: "",
      raises: false,
    };
  }
  const waiting = flag(o.waiting);
  const why = words(o.why);
  return {
    available: true,
    mode,
    waiting,
    why,
    line: waiting
      ? HANDOFF_FRONT.waiting
      : why || (mode === BRING_TO_FRONT
          ? HANDOFF_FRONT.bringToFrontDetail
          : HANDOFF_FRONT.leaveInPlaceDetail),
    lastWords: words(o.last && o.last.message),
    raises: mode === BRING_TO_FRONT,
  };
}

/**
 * The body for one choice, or null when it is not one of the two. Nothing else
 * is ever sent: this route carries one word and no page, picture, title or tap.
 */
export function frontBody(mode) {
  return FRONT_MODES.includes(mode) ? JSON.stringify({ mode }) : null;
}

/** Choosing this one loosens (so it raises a card and waits for a live link). */
export function isLoosening(mode) {
  return mode === BRING_TO_FRONT;
}

/**
 * Every sentence, under the PC's own keys (`WORDS` in
 * backend/jarvis_handoff_front.py), so tests/handoff-front.mjs can hold them to
 * the contract file word for word. Built from HANDOFF_FRONT above, so there is
 * one copy of each sentence in this module, not two.
 */
export const HANDOFF_FRONT_WORDS = Object.freeze({
  title: HANDOFF_FRONT.title,
  detail: HANDOFF_FRONT.detail,
  leave_in_place: HANDOFF_FRONT.leaveInPlace,
  leave_in_place_detail: HANDOFF_FRONT.leaveInPlaceDetail,
  bring_to_front: HANDOFF_FRONT.bringToFront,
  bring_to_front_detail: HANDOFF_FRONT.bringToFrontDetail,
  opens_windows_hello: HANDOFF_FRONT.opensWindowsHello,
  waiting: HANDOFF_FRONT.waiting,
  off_now: HANDOFF_FRONT.offNow,
  damaged: HANDOFF_FRONT.damaged,
});

/** The setting's one route, deliberately not one of the hand-off's own. */
export const FRONT_PATH = "/api/chatbot/handoff_front";
