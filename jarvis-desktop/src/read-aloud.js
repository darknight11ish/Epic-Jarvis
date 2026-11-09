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
 * It also carries the Wave-10 stop (the owner's Q5 ruling, 2026-11-08): the
 * backend publishes the switch on its event bus, and `createReadAloudStop`
 * turns that frame into an immediate halt of the sentence in flight - so OFF
 * is literal mid-answer, not "from the next answer". See its own comment below.
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

/**
 * Wave-10 Q5 / Wave-9 audit F2: OFF reaches a window that is already talking.
 *
 * THE GAP THIS CLOSES. The quickbar read the switch at the START of every voice
 * turn (`main.js` `refreshReadAloud`), so an OFF clicked in Settings - or said
 * in chat/Live, which goes through the same backend route - stopped the NEXT
 * answer, not the sentence in flight. "OFF at once" was therefore not literal.
 * The backend already publishes the change on its own event bus on every set
 * (`backend/jarvis_read_aloud.py` `_publish`: one frame, kind `read_aloud`,
 * `{"enabled": bool}` and nothing else), Rust already fans every bus frame out
 * to every window (`stream.rs` -> the `jarvis-event` Tauri event, which
 * `jarvis-link.js` hands to `onEvent` subscribers), so the missing half is
 * only the consumer: below.
 *
 * WHY IT IS A MODULE AND NOT INLINE IN main.js: the stop has to be provable
 * without a browser. `tests/read-aloud.mjs` drives `createReadAloudStop` with a
 * queue mid-answer and a recording audio stub - the same function `main.js`
 * subscribes - so the test cannot pass by measuring a copy.
 */

/** The one bus kind the switch moves on (backend `jarvis_read_aloud.py`). */
export const READ_ALOUD_KIND = "read_aloud";

/**
 * What one bus frame means for the window: "on", "off", or null for any other
 * frame. A frame without a real boolean is NOT guessed: an unreadable state
 * must never read as off (the same rule `readReadAloud` follows).
 */
export function readAloudFrameAction(frame) {
  if (!frame || frame.kind !== READ_ALOUD_KIND) return null;
  const data = frame.data;
  if (!data || typeof data.enabled !== "boolean") return null;
  return data.enabled ? "on" : "off";
}

/**
 * Stops answer speech NOW, through `io` - getters/setters over the window's own
 * variables, so this file holds no DOM and the test can pass plain values.
 *
 * The order matters: the generation bump first, so a `speak_reply` still being
 * made (or a drain loop already awaiting one) can never start playing it; then
 * the queue and the one-ahead clip; then the sound itself - `pause` is what
 * ends the sentence mid-word, and detaching the handlers keeps its `ended`
 * promise from re-entering the drain; then the promise the player is waiting on
 * is settled; then the flags and the link line.
 *
 * What it does NOT do is mute the rest of the turn (`main.js` `speechMuted`,
 * which a barge-in sets): the switch is a rule, not a one-off. Flipping it back
 * ON mid-answer lets the sentences still arriving be spoken, and every later
 * voice turn re-reads the switch.
 *
 * `io`:
 *   setReadAloudOn(on), bumpGeneration(), dropQueue(), setClipPlaying(bool),
 *   takeAudio() -> audio|null, settleClip(), setSpeaking(bool), sync(),
 *   afterStop?()  - the window's own extra cleanup (moment line, pause waiters)
 */
export function stopSpeechNow(io) {
  io.bumpGeneration();
  io.dropQueue();
  io.setClipPlaying(false);
  const audio = io.takeAudio();
  if (audio) {
    audio.onended = null;
    audio.onerror = null;
    try {
      if (typeof audio.pause === "function") audio.pause();
    } catch (error) {
      // A stopped or already-detached element is not an error worth a line.
    }
  }
  io.settleClip();
  io.setSpeaking(false);
  io.sync();
  if (typeof io.afterStop === "function") io.afterStop();
}

/**
 * Whether a switch READ that started at `startedAtSeq` is still the newest truth,
 * given the event counter now. The two news sources cross: `refreshReadAloud` is
 * a GET issued at the start of a voice turn, and a `read_aloud` event says the
 * switch moved while that GET was in flight. The event is the later truth - the
 * backend publishes it AT the write - so an older snapshot must not overwrite
 * it; a stale "on" landing after an OFF would let the next sentence of the same
 * answer be spoken. Returns true when the read is safe to apply.
 */
export function readStillFresh(startedAtSeq, currentSeq) {
  return startedAtSeq === currentSeq;
}

/**
 * The handler `main.js` gives the event stream: one function, the same one the
 * test drives. Returns the action it took ("on"/"off"/null) so a test can see a
 * frame was understood rather than silently ignored.
 */
export function createReadAloudStop(io) {
  return function onReadAloudFrame(frame) {
    const action = readAloudFrameAction(frame);
    if (action === null) return null;
    io.setReadAloudOn(action === "on");
    if (action === "off") stopSpeechNow(io);
    return action;
  };
}

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
