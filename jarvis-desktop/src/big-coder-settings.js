/**
 * Settings -> Big model (slow) -> "The big coding model (30B coder)".
 *
 * The owner's requirement of 2026-10-22: every feature must be findable AND
 * adjustable in Settings, not only by typing at Jarvis. The big coding model
 * was a real spoken setting (a BoolSetting with a state reader) and a real PC
 * route (`/api/big-coder`, `backend/big-coder.patch`, JARVIS-API section 126),
 * but the desktop had no control for it anywhere.
 *
 * THE ONE PATH. This page calls the new `big_coder` Tauri command, which sends
 * the ONE boolean over the SAME existing route the typed sentence uses. No new
 * mutation path exists: ON is the module's own `set_enabled(true)`, which raises
 * the EXISTING `change_own_config` approval card and changes nothing until the
 * person answers it; OFF is immediate and never held. This page never approves
 * anything and never starts the model - starting the 30B coder pauses Jarvis's
 * own lanes and is the model's separate call, so it is deliberately absent.
 *
 * WHAT THIS WINDOW SHOWS: the switch position, what the PC says it is doing
 * now, and the PC's own disclosure words. It never shows a model file, a path
 * or a card's text from anywhere else.
 *
 * @module big-coder-settings
 */

import { currentLink, linkWords } from "./jarvis-link.js";

const TAURI = globalThis.__TAURI__;
const IS_TAURI = Boolean(TAURI && TAURI.core && TAURI.core.invoke);

const $ = (id) => document.getElementById(id);

const el = {
  body: $("bc-body"),
  reading: $("bc-state"),
  sw: $("bc-switch"),
  line: $("bc-line"),
  linkNote: $("bc-link-note"),
  running: $("bc-running"),
  said: $("bc-status"),
};

const ASKING = "Asking the PC…";
const WAITING_CARD =
  "Waiting for your approval card in the Jarvis bar — the switch stays off " +
  "until it is approved.";
const OFF_ON = "Turn the big coding model on";
const OFF_OFF = "Turn the big coding model off";
const WAITING_LINK =
  "The connection is catching up. Turning the big coding model on asks for " +
  "your approval, so it waits for a live connection; turning it off works at once.";

let view = null;
let busy = false;

function live() {
  return linkWords(currentLink()).canAct;
}

function say(text, tone) {
  if (!el.said) return;
  el.said.textContent = text;
  if (tone) el.said.dataset.tone = tone;
  else delete el.said.dataset.tone;
}

/** The sentence under the switch, from the PC's own status answer. */
function lineWords(v) {
  if (!v || typeof v !== "object") return "";
  if (typeof v.message === "string" && v.message.trim()) return v.message.trim();
  if (v.on !== true) {
    return "Off unless you turn it on here. It is never started on its own.";
  }
  return "On. It starts only when you ask Jarvis for a code job.";
}

/** What the PC says it is doing right now; never guessed from `on`. */
function runningWords(v) {
  if (!v || typeof v !== "object") return "";
  if (v.running === true) {
    return "Running right now. Jarvis's other models are paused while it works.";
  }
  if (v.on === true) return "Loaded as a choice. Nothing is running yet.";
  return "";
}

function paint() {
  if (!el.body) return;
  el.reading.hidden = true;
  el.body.hidden = false;
  if (!view) {
    if (el.sw) el.sw.disabled = true;
    return;
  }
  // Turning it ON raises a card, so it needs a live link; OFF never waits.
  const held = view.on !== true && !live();
  if (el.sw) {
    el.sw.disabled = busy || held;
    el.sw.textContent = view.on === true ? OFF_OFF : OFF_ON;
  }
  if (el.linkNote) {
    el.linkNote.textContent = held ? WAITING_LINK : "";
    el.linkNote.hidden = !held;
  }
  if (el.line) el.line.textContent = lineWords(view);
  if (el.running) {
    const running = runningWords(view);
    el.running.textContent = running;
    el.running.hidden = !running;
  }
}

async function load() {
  if (!el.body || !IS_TAURI) return;
  try {
    view = await TAURI.core.invoke("big_coder", { action: "read" });
  } catch (error) {
    view = null;
    el.body.hidden = true;
    el.reading.hidden = false;
    el.reading.textContent = String((error && error.message) || error ||
      "The PC could not be asked about the big coding model.");
    return;
  }
  paint();
}

async function setSwitch(on) {
  if (busy) return;
  busy = true;
  say(on ? WAITING_CARD : ASKING);
  paint();
  try {
    const out = await TAURI.core.invoke("big_coder", { action: on ? "on" : "off" });
    say((out && out.message) || (on ? "Asked." : "Off."), "ok");
  } catch (error) {
    // The Rust command's own words, verbatim: the stale-link hold, a PC without
    // the route, or the connection's sentence. Never a code.
    say(String((error && error.message) || error), "warn");
  } finally {
    busy = false;
  }
  await load();
}

if (el.body && IS_TAURI) {
  el.sw?.addEventListener("click", () => setSwitch(!(view && view.on === true)));
  load();
} else if (el.reading) {
  el.reading.textContent = "This window cannot ask the PC.";
}
