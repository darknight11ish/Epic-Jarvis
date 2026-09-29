/**
 * What a screen reader is told about Jarvis's face - the same plain sentences
 * the phone says (FaceShellRules.kt `FaceWords`), so the two apps cannot drift
 * apart. `tests/fixtures/face-words.json` holds both to one list.
 *
 * Pure: no window, no DOM. Used by the floating face and the widget (their
 * `#face-status` live region), and by the face page itself when it is opened
 * on its own (faces.html, the canvas's `aria-label`).
 *
 * One sentence per state, one for "not connected" (said whatever pose is
 * showing, and never "notes saved for later" or "idle" about a PC this window
 * cannot hear), and one for a focus session (owner, 2026-09-29): the animal
 * is awake and working beside you, on Quiet, so it will not speak - except
 * for the short line that names a distraction.
 */

/** Said while Jarvis cannot be reached. */
export const OFFLINE_WORDS = "Jarvis isn't connected";

/** Said while a focus session has put Jarvis on Quiet and the focus buddy shows. */
export const FOCUS_WORDS =
  "Jarvis is working beside you in your focus session and will not speak, except to name a distraction";

/** The eight states, by the spec's ids. */
export const STATE_WORDS = Object.freeze({
  error: "Jarvis has a problem",
  approval: "Jarvis is waiting for your decision",
  listening: "Jarvis is listening",
  thinking: "Jarvis is working",
  speaking: "Jarvis is speaking",
  banked: "Jarvis has notes saved for later",
  standby: "Jarvis is on standby and will not speak",
  idle: "Jarvis is idle",
});

/**
 * The sentence for a face signal (jarvis-link.js `faceSignal`): `offline`
 * wins over everything, then a focus session's resting face, then the state.
 * A state this build does not know is said as idle, never as its raw id.
 */
export function faceWords({ state = "idle", offline = false, focus = false } = {}) {
  if (offline) return OFFLINE_WORDS;
  if (focus && state === "idle") return FOCUS_WORDS;
  return STATE_WORDS[state] || STATE_WORDS.idle;
}
