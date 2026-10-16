/**
 * The button that starts the model lane that is down - the desktop half.
 *
 * WHY, AND WHY IT IS A SECOND FILE. `lane-warning.js` is the standing line both
 * windows draw ("The local model isn't running on your PC."), and until now it
 * deliberately did NOTHING: the owner started his lanes, and the app said they
 * were down. The owner has since decided the line should offer one action. The
 * rule module stays exactly as it was - `tests/lane-warning.mjs` pins that it
 * holds no verb for starting anything, and that check is the one that notices
 * if acting ever creeps back into the words - so the action lives here, beside
 * it, and both windows import both files.
 *
 * WHAT THE ONE ACTION IS. Not `ollama serve`, and not a command line built
 * here. The button asks the PC to run ITS OWN Windows logon task for the lane
 * the chat uses (`POST /api/model-lanes/start`), and the PC looks that task up
 * on itself by the half of its name a rename does not touch. That is what a
 * field agent did by hand on 2026-10-13, and it was right precisely because it
 * used the owner's own configuration rather than inventing one.
 *
 * STARTING IS NOT ARRIVING, and this file never says it is. Starting a task
 * returns long before a model is loaded, so pressing the button does not clear
 * the warning: the app ASKS AGAIN, on a short beat, and the warning goes only
 * when the lane really answers. If it does not come up inside the time the PC
 * gives it, the words say so, plainly, and the warning stays standing. A button
 * that reports success and changes nothing is the failure this project keeps
 * finding, so the checks in `tests/lane-start.mjs` are all about that.
 *
 * Pure where it can be: every function here is a function of its arguments, and
 * the one impure thing - how the ask is actually sent - is passed IN
 * (`ask`/`read`), so the tests drive the whole loop without a PC.
 */

/** The button, on the standing line, while the lane is down. One action only. */
export const START_WORDS = "Start the local model";

/** Mid-press, and until the lane either answers or runs out of time. */
export const STARTING_WORDS = "Starting\u2026";

/**
 * What the button is called when a press cannot do anything after all - the
 * lane answers now, or this PC has no such task. Kept apart from
 * [START_WORDS] so a disabled button never promises an action it will refuse.
 */
export const CANNOT_START_WORDS = "Cannot start it";

/**
 * How often the app asks the PC what became of a start it asked for, in
 * milliseconds.
 *
 * Two seconds, and only while a start is in flight: the PC's own answer already
 * carries how long it has been and how long is left (`elapsed_s`, `left_s`), so
 * this is a display beat and not the thing that decides. The PC gives a lane
 * ninety seconds, so at worst this is forty-five small reads of a route that
 * answers from memory.
 */
export const WATCH_BEAT_MS = 2000;

/**
 * The longest this app will keep asking, in milliseconds. The PC's own limit is
 * ninety seconds; this is a little longer so the PC's verdict - "it did not
 * come up" - is the one the owner sees, rather than this app giving up first
 * and inventing a reason of its own.
 */
export const WATCH_LIMIT_MS = 100000;

/**
 * Whether the button is drawn at all, and what it says.
 *
 * `lane` is `GET /api/model-lanes`'s answer, or null when the PC did not
 * answer. NOTHING is drawn for a null: "the PC did not say" is not "the lane is
 * down", which is the same rule the standing line already follows. And it is
 * drawn only when the PC says a press would really do something
 * (`can_start`), so a PC with no such task shows the reason in words instead of
 * a button that would refuse.
 */
export function startButton(lane) {
  if (!lane || typeof lane !== "object") {
    return { show: false, disabled: true, words: "", note: "", state: "" };
  }
  const state = String(lane.state || "");
  if (state === "up") {
    // The lane answered: the standing line clears itself and there is nothing
    // to press. A press that arrives anyway is refused by the PC, not here.
    return { show: false, disabled: true, words: "", note: "", state };
  }
  if (state === "starting") {
    return { show: true, disabled: true, words: STARTING_WORDS,
             note: countdownWords(lane), state };
  }
  if (lane.can_start === true) {
    // `can_start` false with a reason is the PC saying no such task exists, or
    // that it just tried - so the reason is shown and there is no button.
    return { show: true, disabled: false, words: START_WORDS, note: "", state };
  }
  const note = String(lane.message || lane.why || "");
  return { show: false, disabled: true, words: CANNOT_START_WORDS, note, state };
}

/**
 * The line under the button while it is starting: what the PC itself said, or
 * the seconds it has been, or nothing at all. Never a made-up "nearly there".
 */
export function countdownWords(lane) {
  const said = String((lane && lane.message) || "").trim();
  if (said) return said;
  const elapsed = Number(lane && lane.elapsed_s);
  if (Number.isFinite(elapsed) && elapsed > 0) {
    const whole = Math.round(elapsed);
    return `It has been ${whole} second${whole === 1 ? "" : "s"}; this can take up to a minute.`;
  }
  return "Starting it now; this can take up to a minute.";
}

/**
 * What to say when the press could not even be sent, or the PC refused it.
 * Plain, and never softened into a success: the warning stands either way.
 */
export function refusalWords(reply) {
  const said = String((reply && (reply.error || reply.message)) || "").trim();
  return said || "The PC would not start it just now. The local model is still not running.";
}

/**
 * Whether a lane reading is the PC saying the lane is really back. Only the
 * lane answering is - `state: "up"` - and never "starting", which is the whole
 * difference between asking and arriving.
 */
export function laneIsUp(lane) {
  return Boolean(lane) && String(lane.state || "") === "up";
}

/**
 * Ask the PC to start the lane, then keep asking until it settles.
 *
 * The one place the loop lives, so both windows behave identically and
 * `tests/lane-start.mjs` can drive it with no PC at all:
 *
 *   * `ask()` posts the request (the Tauri command, in the real app);
 *   * `read()` reads the lane's state (`GET /api/model-lanes`);
 *   * `wait(ms)` is how the beat is waited out.
 *
 * It resolves with the LAST reading it saw - never with the press's own answer,
 * which is only an acknowledgement. `settled` says whether the lane reached a
 * verdict inside the limit: false means this app stopped asking, and the caller
 * must leave the warning standing and say so rather than pretend.
 *
 * A press the PC refuses resolves at once with the refusal, so the words can be
 * shown and nothing is retried behind the owner's back.
 */
export async function startUntilSettled(ask, read, {
  wait = (ms) => new Promise((resolve) => setTimeout(resolve, ms)),
  beatMs = WATCH_BEAT_MS,
  limitMs = WATCH_LIMIT_MS,
  now = () => Date.now(),
} = {}) {
  let first = null;
  try {
    first = await ask();
  } catch (err) {
    return { ok: false, settled: true, lane: null, refused: true,
             words: refusalWords({ error: String((err && err.message) || err) }) };
  }
  const refused = first && first.ok === false;
  if (refused) {
    return { ok: false, settled: true, lane: null, refused: true,
             words: refusalWords(first) };
  }
  if (laneIsUp(first)) {
    // It was already answering by the time the press arrived: nothing was
    // started, and there is nothing to wait for.
    return { ok: true, settled: true, lane: first, refused: false, words: "" };
  }

  const started = now();
  let last = first;
  while (now() - started < limitMs) {
    await wait(beatMs);
    try {
      last = await read();
    } catch (err) {
      // A read that did not land says nothing about the lane. Keep asking;
      // the limit below is what ends this.
      continue;
    }
    if (laneIsUp(last)) {
      return { ok: true, settled: true, lane: last, refused: false, words: "" };
    }
    if (last && last.state === "down" && last.can_start === false) {
      // The PC has given its verdict: the lane did not come up. Said plainly,
      // and the warning stays standing.
      return { ok: false, settled: true, lane: last, refused: false,
               words: String(last.message || last.why || "") || refusalWords(last) };
    }
  }
  return { ok: false, settled: false, lane: last, refused: false,
           words: "It did not come up in time. The local model is still not running." };
}

/**
 * Draws the button into a page that has `#model-warn` with
 * `#model-warn-start` (the button) and `#model-warn-start-note` (the line under
 * it) inside. Clearing is the same call with an up/unknown reading, so a lane
 * that comes back leaves no mark.
 *
 * The button is created by the page's own markup, not here: a page without it
 * is an older window, and this returns false rather than throwing.
 */
export function paintStartButton(doc, lane, onPress) {
  const root = doc && doc.getElementById ? doc.getElementById("model-warn") : null;
  const button = doc && doc.getElementById ? doc.getElementById("model-warn-start") : null;
  if (!root || !button) return false;
  const view = startButton(lane);
  button.textContent = view.words;
  button.disabled = view.disabled;
  button.hidden = !view.show;
  const note = doc.getElementById("model-warn-start-note");
  if (note) {
    note.textContent = view.note;
    note.hidden = !view.note;
  }
  if (onPress) button.onclick = view.show && !view.disabled ? onPress : null;
  return view.show;
}
