/**
 * Settings -> "The big HUD window" -> "Read replies out loud"
 * (Wave-9, 2026-11-07; jarvis_read_aloud.py, GET/POST /api/read-aloud).
 *
 * TWO Rust commands (src-tauri/src/read_aloud.rs), Settings window only:
 *  - get_read_aloud: the whole switch state, in the PC's own shape;
 *  - set_read_aloud {enabled}: ONE change, cardless in both directions (OFF
 *    removes automatic speech, ON restores the shipped default; neither
 *    loosens a rule, and private-speech.js still keeps a private answer on
 *    screen).
 *
 * THE VALUE IS THE PC'S, NOT THIS WINDOW'S. It is not in localStorage and
 * there is no second copy: a chat or Jarvis Live sentence ("stop reading your
 * replies out loud") changes the SAME value this switch shows and the
 * quickbar's voice answers obey. The state is painted from the PC's answer,
 * never from the click - a save that did not happen reads as not saved.
 *
 * THE PAGE KEEPS ASKING (fixed 2026-11-18, DESKTOP-STATE-DRIFT). The markup row
 * promises "one source of truth, no second copy in this window", but this
 * module used to read the PC once, at module load, and never again: a chat
 * sentence then left the tick and the sentence saying On while the PC said off.
 * It now refreshes through the ONE rule in `settings-live.js` - the PC's own
 * `read_aloud` event, the approval queue, the window coming back into view, and
 * a bounded steady poll - so the row and the PC cannot stay apart.
 *
 * @module read-aloud-settings
 */

import { describeReadAloud, readReadAloud } from "./read-aloud.js";
import { liveRow } from "./settings-live.js";

const TAURI = globalThis.__TAURI__;
const IS_TAURI = Boolean(TAURI && TAURI.core && TAURI.core.invoke);
const $ = (id) => document.getElementById(id);

function problemWords(error) {
  const said = String((error && error.message) || error || "").trim();
  if (!said || /[{}<>]|::|not allowed|undefined|null/i.test(said) || said.length > 400) {
    return "Try again in a moment, or restart Jarvis Desktop.";
  }
  return said;
}

let busy = false;

function paint(state, extra) {
  const box = $("hud-read-replies");
  const line = $("hud-read-replies-status");
  if (box) {
    box.checked = state.known ? state.enabled : false;
    box.disabled = busy || !state.available;
  }
  if (!line) return;
  if (!state.available) {
    line.textContent = state.why || "The read-aloud switch is not available on this PC.";
  } else if (!state.known) {
    line.textContent = state.why;
  } else {
    line.textContent = extra || describeReadAloud(state.enabled);
  }
}

async function load() {
  try {
    if (!IS_TAURI) throw new Error("no desktop backend");
    const reply = await TAURI.core.invoke("get_read_aloud");
    paint(readReadAloud(reply));
  } catch (error) {
    paint({ known: false, enabled: false, available: false,
            why: problemWords(error) });
  }
}

async function save(on) {
  if (busy) return;
  busy = true;
  paint({ known: true, enabled: !on, available: true });
  try {
    const reply = await TAURI.core.invoke("set_read_aloud", { enabled: on });
    paint(readReadAloud(reply));
  } catch (error) {
    // A save that did not happen is shown as not saved, then the real state is
    // read back from the PC so the box never keeps a lie.
    const line = $("hud-read-replies-status");
    if (line) line.textContent = problemWords(error);
    try {
      const back = await TAURI.core.invoke("get_read_aloud");
      paint(readReadAloud(back));
    } catch (ignored) {
      paint({ known: false, enabled: false, available: false,
              why: problemWords(error) });
    }
  } finally {
    busy = false;
    // Re-enable from the load above without repainting over the answer.
    const box = $("hud-read-replies");
    if (box) box.disabled = false;
  }
}

const box = $("hud-read-replies");
if (box) {
  box.addEventListener("change", () => save(Boolean(box.checked)));
  // The ONE refresh rule (settings-live.js): the PC's own `read_aloud` event for
  // a chat or Live sentence, the approval queue, the window coming back into
  // view, and a bounded steady poll. Its first read is this module's first read.
  liveRow({ read: load, kinds: ["read_aloud"] });
}
