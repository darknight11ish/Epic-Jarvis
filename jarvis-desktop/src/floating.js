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
import { faceWords } from "./face-words.js";
import { relayFaceVoice } from "./face-voice.js";
import { relayFaceMoments } from "./face-moments.js";
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

/** Talk-to-type holds this PC's microphone (talk_type.rs sends
 *  `talk-type-listening`): the face shows "listening" while it does, the
 *  same sign the tray icon gives - a local fact the event stream cannot
 *  know, so it wins over what the stream says. */
let talkTypeListening = false;

/** What this window says to a screen reader: the face itself is hidden from
 *  it (decorative), so what it shows is said here instead, in the same eight
 *  plain sentences the phone says, plus "Jarvis isn't connected" and the
 *  focus session's (face-words.js). A polite live region: it speaks when the
 *  face changes, and does not interrupt. */
const status = document.getElementById("face-status");
function sayFace(signal) {
  if (!status) return;
  const words = faceWords(signal);
  if (status.textContent !== words) status.textContent = words;
}

/** Hands the face frame the state to show and the face to wear - the same
 *  message shape widget.js's `postFace` sends. */
function postFace() {
  const signal = faceSignal(currentLink());
  sayFace(signal);
  if (!frame || !frame.contentWindow) return;
  // state, plus `offline` (the "not connected" ring), `waiting` (banked's
  // notches) and `serious` (a crisis answer's calm, plain pose, section
  // 38.1) - jarvis-link.js faceSignal.
  const message = { type: "jarvis-hud-face", ...signal };
  if (talkTypeListening) message.state = "listening";
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
// A fact saved, a long answer ready, a focus session on or off, for the
// animal's nod, glow and focus buddy (face-moments.js) - the same road.
relayFaceMoments(frame, listen, IS_TAURI ? (command) => TAURI.core.invoke(command) : null);
onLink(() => postFace());
// A serious moment starting or ending (the `wellbeing` event) is not a link
// change, so it has its own call to post again.
onSerious(() => postFace());
listen("appearance-changed", () => readFaceAppearance(false));
listen("talk-type-listening", (event) => {
  talkTypeListening = event && event.payload === true;
  postFace();
});
readFaceAppearance(true);
startLink();
// The sun, the moon and the weather behind the animal (sky-feed.js): this
// window may read them (capability sky-read) and keeps what the face frame
// draws in this computer's localStorage - the frame itself holds no command.
startSkyFeed({ onEvent });

/* ---------------------------------------------------------------------------
   CLICK-THROUGH: telling Rust where the face is actually drawn.

   With "Click through to what is behind" on, every click on this window goes
   to whatever is behind it except on the animal. Rust owns the half only it
   can do - it watches the pointer and flips the window's one
   transparent-to-the-pointer switch (`windows.rs`'s own note explains why
   that has to be watched from there). This half owns the half only the page
   can do: knowing where the animal is.

   It has to be measured off the drawn picture rather than worked out from
   the shader's camera. Tried the other way first and measured it: with the
   real shader at the floating window's own framing (front on, zoom 1), every
   one of the five faces reaches the very edge of its square in some pose -
   the red panda's ringed tail to 0.86 of the half-width and its feet to the
   bottom edge, the monkey's vine right across, the owl's branch, the robot's
   shadow - so the only circle that covers an animal is one that also covers
   the whole window, which would let nothing through at all.

   So: the picture is drawn down into a small canvas, and a cell counts as
   the face if it differs at all from the canvas's own top-left pixel, which
   is the background every face paints first (`faces.html`'s common BG). That
   makes it self-calibrating - no colour is written down here, so a theme
   change or the sky cannot make it wrong - and it needs no permission of its
   own: reading the frame's canvas is allowed because this page and that
   frame are the same origin.

   Every doubt goes the same way. If the frame is not there yet, the canvas
   cannot be read, or anything at all throws, an EMPTY grid is sent: Rust
   treats that as "no idea", and a window with no idea takes every click, so
   the animal can never become unclickable (`windows.rs`'s
   `start_floating_hit_watch`). */
const HIT_GRID = 32;
/** Where the face frame's picture is drawn, as HIT_GRID x HIT_GRID cells,
 *  left to right and top to bottom: "1" drawn, "0" background. "" when it
 *  cannot be measured at all. */
function measureHitGrid() {
  try {
    const doc = frame && frame.contentDocument;
    const canvas = doc && doc.getElementById("display-canvas");
    if (!canvas || !canvas.width || !canvas.height) return "";
    const small = document.createElement("canvas");
    small.width = HIT_GRID;
    small.height = HIT_GRID;
    const g = small.getContext("2d", { willReadFrequently: true });
    if (!g) return "";
    g.drawImage(canvas, 0, 0, HIT_GRID, HIT_GRID);
    const px = g.getImageData(0, 0, HIT_GRID, HIT_GRID).data;
    // The background, read off the picture itself rather than written down:
    // the top-left cell is outside every face's own drawing.
    const bg = [px[0], px[1], px[2]];
    const drawn = [];
    for (let i = 0; i < HIT_GRID * HIT_GRID; i++) {
      const o = i * 4;
      const far = Math.abs(px[o] - bg[0]) + Math.abs(px[o + 1] - bg[1]) +
        Math.abs(px[o + 2] - bg[2]);
      drawn.push(far > 30 ? 1 : 0);
    }
    // Grown by one cell in every direction. A cell of this grid is about
    // 6 px on a 200 px window, and the animal is drawn at 30-60 frames a
    // second while this is measured about once a second: without the growth,
    // an ear or a paw that moved between two measurements - or an edge that
    // fell between two cells - would be a place the animal could not be
    // grabbed. Growing it costs a few pixels of background that still take
    // clicks, which is the harmless way round.
    const out = [];
    for (let y = 0; y < HIT_GRID; y++) {
      for (let x = 0; x < HIT_GRID; x++) {
        let on = 0;
        for (let dy = -1; dy <= 1 && !on; dy++) {
          for (let dx = -1; dx <= 1 && !on; dx++) {
            const ny = y + dy, nx = x + dx;
            if (ny < 0 || nx < 0 || ny >= HIT_GRID || nx >= HIT_GRID) continue;
            if (drawn[ny * HIT_GRID + nx]) on = 1;
          }
        }
        out.push(on);
      }
    }
    return out.join("");
  } catch (error) {
    return "";
  }
}

/** Sends the grid to Rust. Never throws: a window that cannot report itself
 *  simply keeps taking every click.
 *
 *  A granted COMMAND rather than an event, and that is the security suite's
 *  doing rather than taste: `core:event:allow-emit` is withheld from every
 *  window on purpose (apps security audit M1), because the quickbar trusts
 *  what it hears and a page that could emit could fake the owner's checked
 *  voice or an approval card. A command is granted to this one window and can
 *  do this one thing (`permissions/surfaces.toml`'s "floating-hit-mask",
 *  `capabilities/floating.json`). */
function reportHitGrid() {
  if (!IS_TAURI) return;
  try {
    const sent = TAURI.core.invoke("note_floating_hit_mask", { grid: measureHitGrid() });
    if (sent && typeof sent.catch === "function") sent.catch(() => {});
  } catch (error) {
    /* no IPC: the window keeps every click, which is the safe way round */
  }
}

// Measured once the face has drawn something, then about once a second: the
// animals breathe, blink and swing, and a grid a second old is a grid whose
// dilation still covers them. Cheap enough to be irrelevant - one 32x32
// read of a picture that is being drawn anyway.
if (frame) frame.addEventListener("load", () => setTimeout(reportHitGrid, 400));
setTimeout(reportHitGrid, 1200);
setInterval(reportHitGrid, 1000);
// A face the owner just picked is a different picture: measure again rather
// than waiting up to a second for the interval.
listen("appearance-changed", () => setTimeout(reportHitGrid, 600));
