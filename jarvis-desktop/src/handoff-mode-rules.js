/**
 * The rules of Settings -> "When the phone does not answer" (the owner's own
 * decision of 2026-10-08: "make this a setting for both options with 1 as the
 * default"; backend/jarvis_handoff_mode.py; docs/CAPTCHA-HANDOFF-DESIGN.md
 * section 5). Pure: no page, no Tauri, so tests/handoff-mode.mjs can run it.
 *
 * The captcha hand-off ("Solve it here") shows a live picture of ONE of the
 * owner's browser windows on their phone, over their private network. This
 * setting is how long it keeps offering it:
 *
 *  - "Stop early" (the DEFAULT): about a minute with nobody looking, then the
 *    hand-off ends and the PC says which window Jarvis is stuck on, so the owner
 *    solves it there;
 *  - "Keep offering it": the full 15-minute ceiling, so the owner can pick their
 *    phone up late. More exposure for a window that may show the owner's own
 *    account details, so choosing it is ONE approval card on the PC with Windows
 *    Hello. Going back is instant.
 *
 * Every sentence is the PC's own (`WORDS` in backend/jarvis_handoff_mode.py):
 * tools/gen_handoff_cases.py carries them into both apps' contract file, and
 * tests/handoff-mode.mjs holds this table to it, so the phone
 * (net/Handoff.kt) says exactly the same.
 *
 * @module handoff-mode-rules
 */

export const HANDOFF_MODE = Object.freeze({
  title: "When the phone does not answer",
  detail:
    "When Jarvis is stuck on a captcha or a sign-in page, your phone can show a live picture of that one window. This chooses how long Jarvis keeps offering it.",
  stopEarly: "Stop early",
  stopEarlyDetail:
    "After about a minute with nobody looking, the hand-off ends and the PC says which window Jarvis is stuck on, so you can solve it there.",
  keepOffering: "Keep offering it",
  keepOfferingDetail:
    "The live picture stays on offer for the full 15 minutes, so you can pick your phone up late. That is more time for that window to be seen, so turning this on asks for your approval.",
  opensWindowsHello:
    "Turning \"Keep offering it\" on asks for your approval on the PC.",
  waiting:
    "Waiting for your approval. The hand-off keeps stopping early until you approve the card.",
  offNow: "Done. The hand-off stops early again when nobody is looking.",
  damaged:
    "the hand-off settings file is damaged, so the hand-off stops early when nobody is looking. Choose \"Keep offering it\" again to rewrite it",
  unread: "Could not read this setting.",
  waitingLink: "Waiting for the connection to your PC.",
  asking: "Asking your PC…",
});

/** The two values, in the PC's order, and the default (the safer one). */
export const MODES = Object.freeze(["stop_early", "keep_offering"]);
export const DEFAULT_MODE = "stop_early";

/** What each choice is called on the screen. */
export const MODE_LABELS = Object.freeze({
  stop_early: HANDOFF_MODE.stopEarly,
  keep_offering: HANDOFF_MODE.keepOffering,
});

/** The one line that says what each choice does. */
export const MODE_HELP = Object.freeze({
  stop_early: HANDOFF_MODE.stopEarlyDetail,
  keep_offering: HANDOFF_MODE.keepOfferingDetail,
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
 * What Settings shows for one GET /api/chatbot/handoff_mode answer. The
 * reference is `view()` in backend/jarvis_handoff_mode.py.
 * -> {available, mode, waiting, why, line, lastWords, idleSeconds, ceilingSeconds}
 */
export function modeView(out) {
  const o = out && typeof out === "object" && !Array.isArray(out) ? out : {};
  const mode = MODES.includes(o.mode) ? o.mode : "";
  if (!mode) {
    return {
      available: false,
      mode: DEFAULT_MODE,
      waiting: false,
      why: "",
      line: HANDOFF_MODE.unread,
      lastWords: "",
      idleSeconds: 0,
      ceilingSeconds: 0,
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
      ? HANDOFF_MODE.waiting
      : why || (mode === "keep_offering"
          ? HANDOFF_MODE.keepOfferingDetail
          : HANDOFF_MODE.stopEarlyDetail),
    lastWords: words(o.last && o.last.message),
    idleSeconds: typeof o.idle_s === "number" ? o.idle_s : 0,
    ceilingSeconds: typeof o.ceiling_s === "number" ? o.ceiling_s : 0,
  };
}

/**
 * The body for one choice, or null when it is not one of the two. Nothing else
 * is ever sent: this route carries one word and no page, picture or tap.
 */
export function modeBody(mode) {
  return MODES.includes(mode) ? JSON.stringify({ mode }) : null;
}

/** Choosing this one loosens (so it raises a card and waits for a live link). */
export function isLoosening(mode) {
  return mode === "keep_offering";
}

/**
 * Every sentence, under the PC's own keys (`WORDS` in
 * backend/jarvis_handoff_mode.py), so tests/handoff-mode.mjs can hold them to
 * the contract file word for word. Built from HANDOFF_MODE above, so there is
 * one copy of each sentence in this module, not two.
 */
export const HANDOFF_MODE_WORDS = Object.freeze({
  title: HANDOFF_MODE.title,
  detail: HANDOFF_MODE.detail,
  stop_early: HANDOFF_MODE.stopEarly,
  stop_early_detail: HANDOFF_MODE.stopEarlyDetail,
  keep_offering: HANDOFF_MODE.keepOffering,
  keep_offering_detail: HANDOFF_MODE.keepOfferingDetail,
  opens_windows_hello: HANDOFF_MODE.opensWindowsHello,
  waiting: HANDOFF_MODE.waiting,
  off_now: HANDOFF_MODE.offNow,
  damaged: HANDOFF_MODE.damaged,
});

/** The setting's one route, deliberately not one of the hand-off's own. */
export const MODE_PATH = "/api/chatbot/handoff_mode";
