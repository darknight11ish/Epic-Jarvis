/**
 * The words on an approval card, and what Jarvis says aloud about a card -
 * the same in the Jarvis bar, the widget, the HUD page and the phone.
 *
 * The creativity audit (2026-09-25, docs/creativity-2026-09-25/experience.md
 * finding 1) found the card speaking three dialects: the bar showed the
 * code name (`switch_model`), the widget "APPROVAL REQUIRED", the phone
 * "Jarvis wants to learning enable", and Approve and Deny swapped places.
 * Now the PC writes every title (backend/jarvis_card_words.py, served as
 * each row's `notice.title`), and every screen shows:
 *
 *   Needs your OK                 <- CARD_KICKER
 *   Jarvis wants to search the web  <- the title (cardTitle)
 *   ...the rest of the card...
 *   [Deny]  [Approve]             <- Deny left, Approve right (CARD_BUTTONS)
 *
 * tests/card-words.mjs holds every word here to
 * tests/fixtures/card-words-cases.json, which tools/gen_card_words_cases.py
 * makes from the backend - the phone's CardWordsContractTest reads the same
 * file, so the two apps cannot word a card differently.
 *
 * No page, no Tauri: node can import it.
 *
 * @module card-words
 */

/** The small label above every card's title. */
export const CARD_KICKER = "Needs your OK";

/** The two buttons, left to right, on every screen. Why this order:
 *  docs/ARCHITECTURE.md §3, "One card on every screen". */
export const CARD_BUTTONS = Object.freeze(["Deny", "Approve"]);

/** The title of a row that names no action at all. */
export const CARD_NO_ACTION = "Jarvis is asking for your approval";

/**
 * What an EXPIRED card says - the one sentence every screen draws, from
 * backend/jarvis_card_words.py's `TIMED_OUT` (2026-10-28, the owner's ruling
 * that the phone's cards must match the desktop's).
 *
 * An expired card cannot be decided any more: the gate refuses it by itself at
 * the deadline, so both apps stop offering the buttons there. This sentence is
 * what explains the empty place they left, and it is one copy so the reason and
 * the dead control cannot drift apart (the DEF-010 lesson).
 */
export const CARD_TIMED_OUT = "Timed out: Jarvis stopped waiting and refused it by itself.";

/**
 * The phone adds this second sentence on the same card, and the PC does not:
 * on the PC the owner is already in front of the window that raises cards, so
 * "ask the desktop" would be advice about a machine he is sitting at. Kept here
 * beside its partner so the pair is read together; `card-words.mjs` holds both
 * against the PC's own words.
 */
export const CARD_TIMED_OUT_NEXT = "Ask the desktop to raise this again.";

/**
 * How long a card has left, in plain words: "14m 59s left", then "42s left"
 * with the warning once it is under a minute.
 *
 * THE OWNER'S RULING OF 2026-10-30: **"if there is a card with a limited time of
 * any kind, be sure to put the timer on it."** His app-builder card ran out
 * twice while he was reading it and no screen had counted it down. What the
 * number counts is the REQUEST's wait - the moment the thread that raised the
 * card stops waiting, which the backend sends as `expires_in` (seconds left)
 * while it is still true. The CARD still has no deadline of its own: 2026-10-28's
 * ruling holds, and nothing is refused because this clock reached zero.
 *
 * The SAME words on every desktop surface, and the same again in the HUD page's
 * `apprClockWords` (it cannot import this file; `tests/expiry-parity.mjs` holds
 * the two together). `""` means "no timer", never "0": a card with no
 * `expires_in` (a pairing, a key registration, a restore) draws no clock at all.
 *
 * Rounding is UP, so a part-second left reads "1s left" rather than showing
 * "0s left" while the request is still there - and "0s" is the one reading both
 * apps treat as "expired now".
 */
export function countdownWords(secondsLeft) {
  const s = Math.ceil(Number(secondsLeft));
  if (!Number.isFinite(s) || s <= 0) return "";
  const minutes = Math.floor(s / 60);
  const words = minutes > 0 ? `${minutes}m ${s % 60}s left` : `${s}s left`;
  return s < 60 ? `${words} \u2014 under a minute to decide.` : words;
}


/**
 * What Jarvis says during a SPOKEN question that waits on a card, and
 * afterwards - keyed by the chat stream's `: jarvis-status` word
 * (backend/jarvis_agent.py: "approval", then the gate's outcome). Fixed
 * sentences: nothing from the card, so safe in any room. There is no
 * approving by voice; these only say where the card is.
 */
export const CARD_VOICE = Object.freeze({
  waiting: "I need your OK for that. There's a card on your screen.",
  approved: "Approved. Carrying on.",
  denied: "OK, I won't do that.",
  timed_out: "That card timed out, so nothing was done.",
});

const CARD_LINES = new Set(Object.values(CARD_VOICE));

/** True for one of the fixed card lines above (never an answer's words). */
export function isCardLine(text) {
  return CARD_LINES.has(text);
}

/**
 * A title for a row with no `notice` (a backend older than
 * approval-notice.patch): the action's name, quoted as a name - the PC's own
 * fallback for an action it has no phrase for (jarvis_card_words.title_for),
 * letter for letter. Never from `prompt` or `detail`: a title also ends up
 * in a Windows notification.
 */
export function fallbackTitle(action) {
  const raw = typeof action === "string" ? action : "";
  const words = raw
    .replace(/_/g, " ")
    .replace(/[^A-Za-z0-9 ]+/g, " ")
    .split(" ")
    .filter(Boolean)
    .join(" ")
    .slice(0, 60)
    .trim();
  return words ? `Jarvis wants your OK for "${words}"` : CARD_NO_ACTION;
}

/** The title every surface shows: the notice's, else the fallback. */
export function cardTitle(approval) {
  if (!approval || typeof approval !== "object") return CARD_NO_ACTION;
  if (typeof approval.title === "string" && approval.title.trim()) return approval.title.trim();
  const notice = approval.notice;
  const title = notice && typeof notice.title === "string" ? notice.title.trim() : "";
  return title || fallbackTitle(approval.action);
}

/**
 * Which card line to say, as the chat stream's status words arrive during
 * ONE spoken question. "approval" says the waiting line once per card; an
 * outcome word says what happened - only after the waiting line was said,
 * so an outcome never arrives out of nowhere. Everything else says nothing.
 * The phone's `CardVoice` does exactly this (the `voice_script` cases).
 */
export function createCardVoice() {
  let waiting = false;
  return {
    /** A new question: nothing said yet. */
    reset() {
      waiting = false;
    },
    /** @returns {string|null} the line to say, or null. */
    onStatus(word) {
      if (word === "approval") {
        if (waiting) return null;
        waiting = true;
        return CARD_VOICE.waiting;
      }
      if (word === "approved" || word === "denied" || word === "timed_out") {
        if (!waiting) return null;
        waiting = false;
        return CARD_VOICE[word];
      }
      return null;
    },
  };
}
