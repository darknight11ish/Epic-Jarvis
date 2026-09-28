/**
 * The floating face's own driver.
 *
 * This page holds `capabilities/floating.json`'s read-only grant
 * (jarvis-link, appearance-read) so the embedded face never has to: it
 * subscribes to the one event stream and the owner's appearance, and hands
 * the embedded `faces.html?mode=display&feed=parent` frame exactly what
 * the Widget's own tray already hands the same frame - see widget.js's
 * `postFace`/`readFaceAppearance`, which this mirrors on purpose rather
 * than inventing a second way to talk to that page.
 */

import { currentLink, onLink, start as startLink, surfaceState } from "./jarvis-link.js";

const TAURI = globalThis.__TAURI__;
const IS_TAURI = Boolean(TAURI && TAURI.core && TAURI.core.invoke);

/** Subscribes to a backend event. No-ops outside Tauri. */
async function listen(event, handler) {
  if (!TAURI || !TAURI.event || !TAURI.event.listen) return () => {};
  try {
    return await TAURI.event.listen(event, handler);
  } catch (error) {
    console.error(`[floating] listen("${event}") failed:`, error);
    return () => {};
  }
}

const frame = document.getElementById("face-frame");

/** The owner's appearance document, as this window last read it. */
let faceAppearance = null;

/** Talk-to-type holds this PC's microphone (talk_type.rs sends
 *  `talk-type-listening`): the face shows "listening" while it does, the
 *  same sign the tray icon gives - a local fact the event stream cannot
 *  know, so it wins over what the stream says. */
let talkTypeListening = false;

/** Hands the face frame the state to show and the face to wear - the same
 *  message shape widget.js's `postFace` sends. */
function postFace() {
  if (!frame || !frame.contentWindow) return;
  const state = talkTypeListening ? "listening" : surfaceState(currentLink());
  const message = { type: "jarvis-hud-face", state };
  if (faceAppearance) message.appearance = faceAppearance;
  try {
    frame.contentWindow.postMessage(message, location.origin);
  } catch (error) {
    /* the frame is mid-navigation; its load event posts again */
  }
}

/**
 * Reads the owner's face. `fromServer` once at boot - `get_appearance` asks
 * Jarvis, so a face or colour changed on the phone arrives - and from
 * memory (`appearance_snapshot`) after that. Never `get_appearance` from
 * inside the `appearance-changed` listener: that command broadcasts the
 * same event, and listening to your own echo is a loop.
 */
async function readFaceAppearance(fromServer) {
  if (!IS_TAURI) return;
  try {
    const doc = await TAURI.core.invoke(fromServer ? "get_appearance" : "appearance_snapshot");
    if (doc && typeof doc === "object") faceAppearance = { face: doc.face || null, bindings: doc.bindings || {} };
  } catch (error) {
    if (fromServer) return readFaceAppearance(false);
  }
  postFace();
}

if (frame) frame.addEventListener("load", postFace);
onLink(() => postFace());
listen("appearance-changed", () => readFaceAppearance(false));
listen("talk-type-listening", (event) => {
  talkTypeListening = event && event.payload === true;
  postFace();
});
readFaceAppearance(true);
startLink();
