/**
 * The PC's automatic read-aloud switch - the words and the normaliser, with no
 * DOM and no Tauri (Wave-9, 2026-11-07).
 *
 * WHAT IT IS. "Read replies out loud", ON by default. The PC's backend holds
 * the one value (`GET/POST /api/read-aloud`, jarvis_read_aloud.py); the
 * Settings window draws it, the quickbar's voice answers obey it, and a chat or
 * Jarvis Live sentence changes it. This module carries the words the page shows
 * and the one reading rule for the PC's answer; `read-aloud-settings.js` is the
 * wiring that calls the two commands.
 *
 * THE TWO RULES IT EXPLAINS, in the owner's own decisions of 2026-11-07:
 *   1. A TYPED question is never read automatically ("if i write it with my
 *      keyboard I would like it not to be read out loud by Default"), so the
 *      switch is about VOICE answers - the quickbar's push-to-talk, Jarvis
 *      Live, "hey Jarvis".
 *   2. A private answer always stays on screen, whatever the switch says
 *      (private-speech.js); the one-answer speaker and "Read out loud" items
 *      are the owner's own taps.
 *
 * @module read-aloud
 */

/** The one route both commands use (the backend's own constant). */
export const READ_ALOUD_PATH = "/api/read-aloud";

/** The shipped default: ON, so nothing the owner hears today changes until he
 *  turns it off. */
export const DEFAULT_ON = true;

/** What a PC without the module is told. */
export const MISSING =
  "Your PC's Jarvis has no read-aloud switch yet - run apply-patches.ps1 on the PC.";

/** The line under the switch. It says the two things a reader has to be able
 *  to trust: a typed question is silent, and a private answer is never read. */
export function describeReadAloud(on) {
  return on
    ? "On: a voice answer - the quickbar's push-to-talk, Jarvis Live, " +
        '"hey Jarvis" - is read aloud in Jarvis\'s voice. A typed question is ' +
        "never read automatically: use the speaker beside an answer, or " +
        '"Read out loud" in its menu. A private answer always stays on screen.'
    : "Off: no voice answer is read aloud automatically. The speaker beside an " +
        'answer and "Read out loud" in its menu still read that one answer when ' +
        "you tap them, and a private answer still stays on screen.";
}

/**
 * The PC's answer, read once. Returns
 * `{known, enabled, available, why, words}` - never a guessed state:
 *  - a 2xx with a real boolean is the PC's answer, word for word;
 *  - a missing module (`available: false`, or a 404/503) is `available: false`
 *    with the PC's own sentence, and `enabled` stays the shipped default;
 *  - anything unreadable is `known: false`, drawn as "could not read", never
 *    as "off" (a state that cannot be read is not the same as a switch off).
 */
export function readReadAloud(reply) {
  if (reply && reply.available === false) {
    return { known: false, enabled: DEFAULT_ON, available: false,
             why: String(reply.why || MISSING), words: "" };
  }
  if (reply && typeof reply === "object"
      && typeof reply.enabled === "boolean") {
    return { known: true, enabled: reply.enabled, available: true, why: "",
             words: String(reply.words || "") };
  }
  return { known: false, enabled: DEFAULT_ON, available: true,
           why: "Jarvis answered, but not in a way this app can read. " +
                "Update the backend by running apply-patches.ps1.",
           words: "" };
}
