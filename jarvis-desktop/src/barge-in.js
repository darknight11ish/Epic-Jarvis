/**
 * "Interrupt Jarvis while it talks" on this PC: the setting and its words.
 *
 * The desktop twin of the phone's BargeIn switch (StopWord.kt `BargeIn`,
 * ClientSettings.kt), and what it controls here, decided from the code:
 *
 * While this PC listens for "hey Jarvis" (voice.rs, `run_vad_loop`), it
 * keeps listening while Jarvis speaks a reply. Two things can then cut the
 * reply off: the word "stop" (the server answers `stop: true`) and "hey
 * Jarvis" itself (`wake_heard`) - voice.rs emits `voice-speech-started` for
 * both, and the Jarvis bar (main.js) silences the reply. A "hey Jarvis"
 * sentence heard over the reply is also sent as a new question.
 *
 * ON (the default - it is how this PC has always behaved): all of that, as
 * before - and, since 2026-09-25, talking over a reply (voice-flow.js,
 * voice_flow.rs): half a second of speech pauses it, and the PC says
 * whether it was the owner (stop) or not (carry on). OFF: while Jarvis is talking, the Jarvis bar ignores what the
 * listener hears - no "stop", no "hey Jarvis", no new question - until the
 * reply has finished. The reply can still be stopped with Esc in the Jarvis
 * bar. (Holding the talk button is not a way round it: push-to-talk is
 * refused while "hey Jarvis" listening has the microphone.) This is honest about
 * one difference from the phone: the phone's microphone stops listening
 * while Jarvis talks; this PC's listener still hears and checks what is said
 * (on this PC only, the same loopback path as always), and the Jarvis bar
 * throws the answer away. The words below say "ignored", not "not
 * listening", for that reason.
 *
 * Why ON by default when the phone's default follows its echo canceller:
 * this PC cannot know whether Windows' echo cancelling works until listening
 * starts (aec.rs), and the listener already did all of the above before this
 * switch existed. The server also guards the PC's own case: it ignores
 * "stop" for 30 s after Jarvis itself said the word, and "hey Jarvis" must
 * pass the owner's voice check.
 *
 * Per computer and never synced, like the phone's (which is per phone): it
 * lives in this window origin's localStorage, shared by the Settings window
 * that changes it and the Jarvis bar that reads it.
 *
 * @module barge-in
 */

/** The localStorage key. */
export const BARGE_IN_KEY = "jarvis.voice.bargeIn";

/** The switch's name, the phone's words. */
export const BARGE_IN_NAME = "Interrupt Jarvis while it talks";

/** The owner's setting, or ON when none was saved (or storage is unreadable). */
export function loadBargeIn(storage = globalThis.localStorage) {
  try {
    const saved = storage && storage.getItem(BARGE_IN_KEY);
    if (saved === "off") return false;
  } catch {
    /* private mode or cleared site data: the default */
  }
  return true;
}

/** Saves the setting. Returns whether it could be saved. */
export function saveBargeIn(on, storage = globalThis.localStorage) {
  try {
    if (!storage) return false;
    storage.setItem(BARGE_IN_KEY, on ? "on" : "off");
    return true;
  } catch {
    return false;
  }
}

/**
 * Whether a "stop", a "hey Jarvis" or a sentence heard by the listener is
 * thrown away: only with the switch off, and only while Jarvis is talking.
 */
export function ignoreWhileTalking(bargeIn, talking) {
  return !bargeIn && Boolean(talking);
}

/** The switch's line in Settings - the phone's `BargeIn.describe`, for a PC. */
export function describeBargeIn(on) {
  return on
    ? "On: while Jarvis talks, this PC keeps listening. Say \"stop\" to silence it, or \"hey Jarvis\" " +
        "to cut in with something new. Or just start talking: Jarvis pauses, and stops if your PC " +
        "hears it is you. It hears you best when Windows' echo cancelling is working; " +
        "the Jarvis bar says when it is."
    : "Off: while Jarvis talks, what this PC hears is ignored, even \"stop\" and \"hey Jarvis\". " +
        "To stop a reply, press Esc in the Jarvis bar until it closes.";
}
