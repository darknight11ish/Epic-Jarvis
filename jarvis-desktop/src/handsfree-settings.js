/**
 * Settings -> Hands-free mode (2026-11-04, the owner's own request; backend
 * `jarvis_handsfree.py`, JARVIS-API section 191).
 *
 * Two Rust commands (`src-tauri/src/handsfree.rs`), Settings only:
 *  - get_handsfree: is the mode on, the answer window, and whether a phone can
 *    take a text - a read;
 *  - set_handsfree {enabled}: the switch. OFF by default. **ON raises ONE
 *    approval card** (`handsfree_enable`, a risky one: it changes what an
 *    approval needs from then on). The Rust command waits 20 s
 *    (`handsfree.rs` WRITE_TIMEOUT) while the card itself waits up to 15
 *    minutes (`jarvis_gate.py` APPROVAL_TIMEOUT = 900 s), so the call may end
 *    long before a person answers. This page therefore draws a waiting line,
 *    marks the tick UNCONFIRMED (a dash, never a state) and keeps re-reading
 *    through `settings-live.js` until the PC answers - the timeout sentence is
 *    never put on a card that is simply still waiting. **OFF is immediate and
 *    cardless.**
 *
 * This page decides NOTHING. The card it raises is answered on the PC or the
 * phone through the same `/api/approve` every card uses; there is no second
 * permission path, and no control here answers a card.
 *
 * The words below are the PC's own, kept byte for byte as the fallback for a
 * read that fails or a PC that answers without them, the same copy
 * asks-first.js keeps for its own rows. `tests/handsfree-settings.mjs` holds
 * them to the Python module.
 *
 * @module handsfree-settings
 */

import { announce } from "./jarvis-link.js";
import { liveRow, looksLikeATimeout } from "./settings-live.js";

const TAURI = globalThis.__TAURI__;
const IS_TAURI = Boolean(TAURI && TAURI.core && TAURI.core.invoke);
const $ = (id) => document.getElementById(id);

/* ── The PC's own words, byte for byte (jarvis_handsfree.LABEL/DETAIL) ───── */

export const LABEL = "Hands-free mode";

export const DETAIL =
  "Off (the default): every card needs a tap, exactly as it always has. " +
  "On: every approval card that starts waiting is read out to your phone, and " +
  "one word - yes, yeah, confirm, approve, do it, go ahead, okay, or no, nope, " +
  "deny, cancel, stop, don't - answers THAT one card, within a minute of " +
  "hearing it. It also answers the cards that would otherwise wait for Windows " +
  "Hello or your phone's fingerprint; that is the part to understand before " +
  "turning it on. The words are made on your PC, never by the phone; Jarvis " +
  "checks the voice is yours BEFORE it turns the clip into words; with no " +
  "voice trained it will not take a spoken yes at all; and one card gets one " +
  "decision - an unclear answer is asked once more and then treated as a no. " +
  "Turning it on raises one approval card. Turning it off is instant and asks " +
  "nothing.";

export const HEADING = "Hands-free mode";

/** This app's own line for a PC whose Jarvis has no such route yet - byte for
 *  byte Rust's `handsfree::HANDSFREE_MISSING`. */
export const MISSING =
  "Your PC's Jarvis does not have hands-free mode yet - run apply-patches.ps1 on the PC.";

export const ON_SAID = "Hands-free mode is on. Say one word from the list when a card is read out.";
export const OFF_SAID = "Hands-free mode is off. Cards need a tap again.";
/** While the 20 s Rust wait has ended but the card's own 15-minute gate is
 *  still open. The tick beside it is drawn as a dash (unconfirmed), never as
 *  the last value, so the row cannot show a stale state as the current one. */
export const WAITING = "Waiting for your approval on the PC…";

/** The card's own elements. A function, never read at module load: the suite
 *  imports this module in plain Node, where there is no document. */
function els() {
  return {
    section: $("handsfree"),
    state: $("hf-state"),
    body: $("hf-body"),
    enabled: $("hf-enabled"),
    label: $("hf-enabled-label"),
    detail: $("hf-enabled-detail"),
    enabledStatus: $("hf-enabled-status"),
    status: $("hf-status"),
    window: $("hf-window"),
    phone: $("hf-phone"),
  };
}

const IN_WINDOW = typeof document !== "undefined" && typeof globalThis.document === "object";

let view = null;
let busy = false;
/** A carded ON may still be waiting in the Jarvis bar. While this is true the
 *  tick is drawn UNCONFIRMED and the line says so; `live` keeps re-reading. */
let awaiting = false;
/** The ONE refresh rule (`settings-live.js`); it owns when to ask again. */
let live = null;

function words(v) {
  return typeof v === "string" ? v : "";
}

function say(target, line, tone) {
  if (!target) return;
  target.textContent = line;
  if (tone) target.dataset.tone = tone;
  else delete target.dataset.tone;
}

/** An error in words, never a bridge error or JSON. */
function problemWords(error) {
  const said = String((error && error.message) || error || "").trim();
  if (!said || /[{}<>]|::|not allowed|undefined|null/i.test(said) || said.length > 400) {
    return "Try again in a moment, or restart Jarvis Desktop.";
  }
  return said;
}

/**
 * `get_handsfree`'s answer, read. A 2xx whose body this app cannot read is
 * `available: false` with the PC's own sentence - never "off", because a state
 * that cannot be read is not a mode that is switched off.
 */
export function readHandsfree(answer) {
  const a = answer && typeof answer === "object" ? answer : {};
  const window_sec = Number.isFinite(a.window_sec) && a.window_sec > 0 ? Math.round(a.window_sec) : 60;
  if (a.available === false) {
    return { available: false, why: words(a.why) || MISSING, on: false, window_sec };
  }
  return {
    available: true,
    on: a.enabled === true,
    window_sec,
    label: words(a.label) || LABEL,
    detail: words(a.detail) || DETAIL,
    heading: words(a.heading) || HEADING,
  };
}

/** `set_handsfree`'s answer: did the mode really move, and what did the PC say?
 *  A denial is the PC's own sentence, never a green "saved" over a refused card. */
export function readChange(answer) {
  const a = answer && typeof answer === "object" ? answer : {};
  return {
    enabled: a.enabled === true,
    changed: a.changed === true,
    message: words(a.message),
  };
}

/** The one control is greyed only while a change is in flight. */
function syncBusy() {
  const pc = els();
  if (pc.enabled) pc.enabled.disabled = busy;
}

function paint() {
  const pc = els();
  if (!view) return;
  if (!view.available) {
    say(pc.state, view.why, "warn");
    if (pc.body) pc.body.hidden = true;
    return;
  }
  say(pc.state, "");
  if (pc.body) pc.body.hidden = false;
  if (pc.enabled) {
    pc.enabled.checked = view.on;
    // Never paint a value whose card is still waiting as if it were current.
    pc.enabled.indeterminate = awaiting === true;
  }
  if (pc.label) pc.label.textContent = view.label;
  if (pc.detail) pc.detail.textContent = view.detail;
  if (pc.window) {
    pc.window.textContent =
      `A spoken answer is open for ${view.window_sec} seconds after a card is read out.`;
  }
  if (awaiting) say(pc.enabledStatus, WAITING, "waiting");
  else if (pc.enabledStatus && pc.enabledStatus.dataset.tone === "waiting") {
    say(pc.enabledStatus, "");
  }
  syncBusy();
}

async function refresh() {
  const pc = els();
  const wasAwaiting = awaiting;
  try {
    if (!IS_TAURI) throw new Error(MISSING);
    // The command names are written out at each call site rather than through a
    // wrapper, so tools/check_invoke_grants.py can read them without a
    // DYNAMIC_BELOW entry - the same rule prompt-coach-settings.js follows.
    const answer = await TAURI.core.invoke("get_handsfree", {});
    view = readHandsfree(answer);
  } catch (error) {
    // A failed read is NOT "off": it is a card that cannot say.
    view = { available: false, why: problemWords(error), on: false, window_sec: 60 };
  }
  if (awaiting) {
    // The PC has answered (the mode moved), or it cannot answer at all, or the
    // card's own 15-minute window has closed and its last answer is final.
    const answered = view.on === true || view.available === false;
    const expired = live ? !live.pending() : false;
    if (answered || expired) {
      awaiting = false;
      live?.release();
    }
  }
  paint();
  if (wasAwaiting && !awaiting && view.available) {
    say(pc.enabledStatus, view.on ? ON_SAID : OFF_SAID, "ok");
    if (view.on) announce?.(ON_SAID);
  }
  if (pc.state && !view.available) announce?.(view.why);
  return view;
}

async function flip(on) {
  const pc = els();
  if (busy) return;
  busy = true;
  syncBusy();
  if (on) {
    // The mode is not on yet: the PC says off until a person answers the card,
    // so the tick is drawn as unconfirmed (a dash) from the moment it is asked.
    awaiting = true;
    live?.hold();
    say(pc.enabledStatus, WAITING, "waiting");
    paint();
  } else {
    say(pc.enabledStatus, "");
  }
  try {
    if (!IS_TAURI) throw new Error(MISSING);
    const answer = readChange(
      await TAURI.core.invoke("set_handsfree", { enabled: Boolean(on) }),
    );
    awaiting = false;
    live?.release();
    say(pc.enabledStatus, answer.message || (answer.enabled ? ON_SAID : OFF_SAID),
        answer.enabled === on ? "ok" : "warn");
  } catch (error) {
    if (on && looksLikeATimeout(error)) {
      // The Rust call gave up after 20 s but the card's 15-minute gate is still
      // open, so this is NOT a failed save: say the truth and keep reading. The
      // bridge's "restart Ollama" sentence has nothing to do with it.
      awaiting = true;
      live?.hold();
      say(pc.enabledStatus, WAITING, "waiting");
      paint();
      announce?.(WAITING);
    } else {
      awaiting = false;
      live?.release();
      say(pc.enabledStatus, problemWords(error), "warn");
      // A denied card leaves the mode off; read it back rather than guess.
      if (on) announce?.(problemWords(error));
    }
  } finally {
    busy = false;
    await refresh();
  }
}

function wire() {
  const pc = els();
  if (!pc.enabled) return;
  pc.enabled.addEventListener("change", () => {
    const wanted = Boolean(pc.enabled.checked);
    flip(wanted);
  });
  // The ONE refresh rule (settings-live.js): the approval queue (the card was
  // answered), the window coming back into view, and a bounded steady poll.
  // Its first read is this page's first read.
  live = liveRow({ read: refresh });
}

if (IN_WINDOW) {
  // The page is one document; this module is loaded once at the end of it.
  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", wire);
  } else {
    wire();
  }
}
