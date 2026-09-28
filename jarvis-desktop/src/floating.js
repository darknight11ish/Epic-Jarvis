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

import { currentLink, faceSignal, onEvent, onLink, onSerious, start as startLink } from "./jarvis-link.js";
import { relayFaceVoice } from "./face-voice.js";
import { startSkyFeed } from "./sky-feed.js";

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

/** The one thing this window says to a screen reader: the face itself is
 *  hidden from it (decorative), so "not connected" is said here instead. */
const status = document.getElementById("face-status");
function sayConnection(offline) {
  if (!status) return;
  const words = offline ? "Jarvis isn't connected" : "";
  if (status.textContent !== words) status.textContent = words;
}

/** Hands the face frame the state to show and the face to wear - the same
 *  message shape widget.js's `postFace` sends. */
function postFace() {
  const signal = faceSignal(currentLink());
  sayConnection(signal.offline);
  if (!frame || !frame.contentWindow) return;
  // state, plus `offline` (the "not connected" ring), `waiting` (banked's
  // notches) and `serious` (a crisis answer's calm, plain pose, section
  // 38.1) - jarvis-link.js faceSignal.
  const message = { type: "jarvis-hud-face", ...signal };
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
// Lip-sync: Jarvis's voice and the owner's microphone, passed into the face
// the same way (face-voice.js) - an event reaches this page, never its frame.
relayFaceVoice(frame, listen);
onLink(() => postFace());
// A serious moment starting or ending (the `wellbeing` event) is not a link
// change, so it has its own call to post again.
onSerious(() => postFace());
listen("appearance-changed", () => readFaceAppearance(false));
readFaceAppearance(true);
startLink();
// The sun, the moon and the weather behind the animal (sky-feed.js): this
// window may read them (capability sky-read) and keeps what the face frame
// draws in this computer's localStorage - the frame itself holds no command.
startSkyFeed({ onEvent });
