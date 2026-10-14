/**
 * Jarvis restarted the local model by itself - said on both desktop windows,
 * and the switch that lets the owner tell it not to.
 *
 * WHY THIS EXISTS. `lane-warning.js` is the standing line both windows draw
 * ("The local model isn't running on your PC.") and PR #409 made it deliberately
 * act on nothing. `lane-start.js` is the one action the owner can press. NEITHER
 * ANSWERS THE DEFECT: his lanes die at 08:19 with nobody at a screen - the PC's
 * own Task Scheduler still reporting Result=0 State=Ready - and the owner
 * decided on 2026-10-14: *"Also restart the lane automatically when it dies."*
 * The BACKEND now does that (`backend/jarvis_model_lanes.py`), on its own
 * thread, and this file is the desktop half of being TOLD.
 *
 * A SILENT AUTO-RESTART WOULD BE A CHANGE TO HIS MACHINE HE DID NOT MAKE, so
 * nothing here is left to be noticed by inference. The backend writes the
 * sentence - "Jarvis started the local model again at 08:19, because it was not
 * running." - and carries it in `GET /api/model-lanes`'s `auto_note`. THIS FILE
 * DRAWS THAT STRING AND COMPOSES NOTHING: one place writes the words, so the
 * bar, the widget and the phone cannot come to three different ways of saying
 * one fact. That is the same rule the approval notice follows
 * (`docs/ARCHITECTURE.md` §3).
 *
 * THE SENTENCE MUST BE ABLE TO APPEAR WHILE THE LANE IS UP, which is why it is
 * its own element and not part of `#model-warn`: the standing line is hidden
 * the moment the lane answers, and "it came back" is exactly the moment the
 * owner needs to hear about. Its own element also means the two halves cannot
 * fight over one `hidden` flag.
 *
 * AND IT MUST BE ABLE TO SAY THE OPPOSITE. A dead process carries no intent:
 * "it crashed" and "I closed it on purpose" are the same fact from the PC. So
 * the answer is not a cleverer test, it is this switch - off in one press,
 * immediate, no card (it only narrows what Jarvis does; turning it back on is
 * the same action the button beside it takes in the same second, so a card
 * would be stricter than the button). The residual risk is real and is stated
 * rather than hidden: with the switch on, Jarvis will start a lane the owner
 * stopped deliberately, and this line is how he finds out it did.
 *
 * Pure where it can be: [autoNotice] is a plain function of its argument, so
 * `tests/lane-auto.mjs` holds the rule and the sentences without a browser.
 * [paintAutoNotice] is the one DOM half, shared by both windows so they cannot
 * drift apart.
 */

/**
 * The switch's own label while it is ON: the press turns the automatic restart
 * OFF. Written here and in `jarvis-client`'s `ModelLane.kt` (`AUTO_SWITCH_OFF`)
 * because both apps are offering one action on one fact - the same rule the
 * "Start the local model" button already follows in `lane-start.js` and
 * `ModelLane.kt`.
 */
export const AUTO_SWITCH_OFF_WORDS = "Don't restart it for me";

/** And while it is OFF: the press turns it back on. Immediate, no card. */
export const AUTO_SWITCH_ON_WORDS = "Restart it automatically again";

/**
 * The one field this file reads. `undefined` means an OLDER BACKEND that does
 * not report the switch at all - and then NOTHING is drawn: a window must not
 * invent a switch, or offer to turn off something that was never on. `true` is
 * the switch on (which is what a backend with the feature defaults to), `false`
 * is the owner having turned it off.
 */
export function autoSwitchOn(lane) {
  if (!lane || typeof lane !== "object") return undefined;
  return typeof lane.auto === "boolean" ? lane.auto : undefined;
}

/**
 * Whether the line is drawn at all, what it says, and what its button does.
 *
 * `null` or an absent reading draws NOTHING: "the PC did not say" is not "Jarvis
 * restarted something", which is the same rule the standing line already
 * follows for an absent `ollama` field.
 *
 * The words are the backend's own sentence, verbatim - `auto_note`. It is
 * non-empty whenever there is something to say, including "Jarvis is not
 * starting the local model by itself: automatic restarting is off.", which the
 * backend reports whenever the switch is off, so there is always one press
 * available to turn it back on. A window therefore never has to decide whether
 * a fact is worth mentioning.
 */
export function autoNotice(lane) {
  if (!lane || typeof lane !== "object") {
    return { show: false, words: "", switchWords: "", switchTo: null, capped: false };
  }
  const words = String(lane.auto_note || "").trim();
  const on = autoSwitchOn(lane);
  const switchWords = on === true ? AUTO_SWITCH_OFF_WORDS
    : on === false ? AUTO_SWITCH_ON_WORDS : "";
  return {
    show: words !== "",
    words,
    switchWords,
    // What the press asks the PC for - never what the app will claim happened.
    switchTo: on === true ? false : on === false ? true : null,
    capped: lane.auto_capped === true,
  };
}

/**
 * Draws (or clears) the line in a page that has `#model-auto` with
 * `#model-auto-text` and `#model-auto-switch` inside it.
 *
 * `failure` is the PC's own refusal sentence, or this app's plain one when the
 * press never landed. It replaces the line rather than clearing it, and the
 * button is disabled while it stands: a switch that reports a change it did not
 * make would be the same defect as a button that reports a success it did not
 * have.
 *
 * Clearing is the same call with a reading that says nothing, so a lane that
 * comes back - and a switch that is on - leaves no mark. A page without the
 * element is an older window, and this returns false rather than throwing.
 */
export function paintAutoNotice(doc, lane, onSwitch, failure = "") {
  const root = doc && doc.getElementById ? doc.getElementById("model-auto") : null;
  const text = doc && doc.getElementById ? doc.getElementById("model-auto-text") : null;
  // No row, or no place to write the words in it: false, and nothing thrown. A
  // page without both is an older window, and the same answer
  // `paintStartButton` gives for a page without its button.
  if (!root || !text) return false;
  const button = doc.getElementById("model-auto-switch");
  const view = autoNotice(lane);
  const said = String(failure || "").trim();
  const words = said || view.words;
  text.textContent = words;
  if (button) {
    button.textContent = view.switchWords;
    button.hidden = !view.show || !view.switchWords;
    button.disabled = Boolean(said);
    if (onSwitch && view.show && !said && view.switchTo !== null) {
      button.onclick = () => onSwitch(view.switchTo);
    } else {
      button.onclick = null;
    }
  }
  root.hidden = !words;
  return Boolean(words);
}
