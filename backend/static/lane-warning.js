/**
 * When the local model is not reachable, said standing - before any question,
 * and in the same words in both desktop windows.
 *
 * WHY THIS EXISTS. On 2026-10-13 the owner's two Ollama lanes (the everyday
 * model on 11436, the coding model on 11435) were both dead from about 16:30
 * until about 21:5x. Nothing restarted them, and nothing said so: the
 * scheduled tasks still reported "last run 09:11, result 0", and both apps
 * still looked connected. Jarvis only admitted it when he asked something,
 * with the chat error `model_not_running`. The fact was on the wire the whole
 * time - the backend's `GET /api/status` carried `"ollama": false`
 * (`jarvis_hud.py`, `_reachable(OLLAMA_URL + "/api/tags")`, the SAME address
 * the chat itself uses, so a lane on another port is judged where it really
 * is) - and neither app drew it.
 *
 * THE STATE IS ITS OWN, not "Jarvis isn't connected". The two mean opposite
 * things about the PC: "Jarvis isn't connected" is this device unable to
 * reach the PC at all, while this one is the PC answering perfectly and its
 * own model server being down. Saying "isn't connected" over a live PC is the
 * exact confusion the 2026-10-09 note in `hud_bootstrap.js` was written to
 * end, so this warning never borrows those words.
 *
 * THE WORDS. Plain, calm, no jargon: the owner is a beginner, so "Ollama"
 * appears only in brackets, after the plain phrase, and only to say which
 * program to open. No exclamation, no red, no dialog - and nothing here acts.
 * It does not start, restart or change anything: the owner starts his lanes,
 * and the app tells him they are down.
 *
 * Pure where it can be: [laneWarning] and [hostWords] are plain functions of
 * their arguments, so `tests/lane-warning.mjs` holds them to the sentences and
 * to the sources that report them. [paintLaneWarning] is the one DOM half,
 * shared by the HUD window so the two windows cannot drift apart.
 */

/** The line a window shows while the PC says its local model is not reachable. */
export const LANE_DOWN_WORDS = "The local model isn't running on your PC.";

/**
 * How often a desktop window asks whether the PC's own model is running, in
 * milliseconds. One number for both windows that ask (the widget and the bar),
 * because they are watching one fact between them.
 *
 * Nothing on the event bus reports a lane dying, so a probe is the only way to
 * hear it - and the incident this exists for (2026-10-13: both of the owner's
 * lanes dead for about five hours, the apps looking healthy) is exactly what
 * boot-only probing produced. Deliberately longer than a minute:
 * `tests/timers.mjs` requires that an idle wait is at least the idle minute and
 * counts wake-ups inside a simulated minute, so a beat under 60 s would put a
 * wake-up back into a window that audit emptied. It is three loopback requests
 * against two local servers, for a fact that changes at most a few times a day.
 */
export const HEALTH_BEAT_MS = 90000;

/**
 * What to do about it. The lanes are started by the owner's own scheduled
 * tasks (`start-lane.ps1`), so the useful instruction is the one he already
 * uses at a terminal.
 */
export const LANE_DOWN_FIX =
  "Open Ollama on the PC, or run ollama serve there. This window will say when it is back.";

/**
 * Whether the warning is drawn, from the one field the PC reports.
 *
 * `ollama` is `GET /api/status`'s own boolean (`jarvis_hud.py:3206`,
 * `_reachable(OLLAMA_URL + "/api/tags")`).
 *
 * `true` - the PC answers for its model: nothing is drawn.
 * `false` - the PC says its model is not there: the line is drawn.
 * `null`/`undefined` - the PC did not say, because the read did not land or an
 * older backend has no such field. NOTHING is drawn: "unknown" is not "down",
 * and a warning that appears whenever a read fails is one more thing the owner
 * learns to ignore.
 */
export function laneWarning(ollama) {
  if (ollama === false) {
    return { down: true, words: LANE_DOWN_WORDS, fix: LANE_DOWN_FIX };
  }
  return { down: false, words: "", fix: "" };
}

/**
 * The beat both desktop windows ask on: `probe()` when the window is on screen
 * and nothing is already in flight, then the same wait again. Never faster than
 * [HEALTH_BEAT_MS], and it does not drift into a spin when a probe is slow -
 * the wait is re-armed after each attempt, in `finally`.
 *
 * Shared rather than copied so the two windows cannot come to different
 * cadences, and so `tests/lane-warning.mjs` can hold the rule without a browser.
 * Returns a stop function.
 */
export function startHealthBeat(probe, { doc = document, waitMs = HEALTH_BEAT_MS, schedule = setTimeout, cancel = clearTimeout } = {}) {
  let stopped = false;
  let armed = null;
  const tick = async () => {
    if (stopped) return;
    try {
      if (!(doc && doc.hidden)) await probe();
    } finally {
      if (!stopped) armed = schedule(tick, waitMs);
    }
  };
  armed = schedule(tick, waitMs);
  return () => {
    stopped = true;
    if (armed !== null) cancel(armed);
    armed = null;
  };
}

/**
 * The host's own line, under the model warning: which of the two things is
 * actually wrong. `connected` is the shell's live stream verdict, never a
 * read that succeeded a moment ago, and `null` means the shell has not said
 * yet - which is not a claim that the PC is down, so it is not drawn either.
 */
export function hostWords(connected) {
  if (connected === true) return "The PC is answering - Jarvis' own model server is not.";
  if (connected === false) return "Jarvis is not answering either.";
  return "";
}

/**
 * Draws (or clears) the warning in a page that has `#model-warn` with
 * `#model-warn-text`, `#model-warn-fix` and `#model-warn-host` under it.
 *
 * Clearing is the same call with an up/unknown reading, so a lane that comes
 * back clears itself and leaves no mark: there is no state kept between calls
 * except the last drawn one.
 */
export function paintLaneWarning(doc, ollama, connected) {
  const root = doc && doc.getElementById ? doc.getElementById("model-warn") : null;
  if (!root) return false;
  const warn = laneWarning(ollama);
  const text = doc.getElementById("model-warn-text");
  const fix = doc.getElementById("model-warn-fix");
  const host = doc.getElementById("model-warn-host");
  if (text) text.textContent = warn.words;
  if (fix) fix.textContent = warn.fix;
  if (host) {
    // The host's line belongs to the warning, and only to it: with no warning
    // to explain, it is hidden whether or not a host verdict is known.
    const words = warn.down ? hostWords(connected) : "";
    host.textContent = words;
    host.hidden = !words;
  }
  root.hidden = !warn.down;
  return warn.down;
}
