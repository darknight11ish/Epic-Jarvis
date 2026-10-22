/**
 * Settings -> Security -> "Chat history on this PC".
 *
 * Task-79 (owner requirement of 2026-10-22: every feature findable AND
 * adjustable in Settings) plus voiceprint-wiring's #734 typed settings
 * `chat_history` and `chat_keep_days`. Before this, the only UI for either was
 * the Brain's History tab.
 *
 * THE ONE PATH. Both controls call the new `history_settings` Tauri command,
 * which uses the EXISTING route `/api/history/settings` - the same route (and
 * the same `jarvis_chat_log.request_settings` function) the typed layer and the
 * Brain switch use. Plain English: `{"enabled": true|false}` or
 * `{"keep_days": 0|30|90|365}`, ONE field per request, exactly as the route
 * documents.
 *
 * WHAT THE PAGE MAY SEE. Only the status fields. The read asks Rust for the
 * status; the conversation list the route carries is DROPPED IN RUST, so no
 * chat word, title or id ever reaches this window. This page has no delete, no
 * search and no conversation list, and the command cannot reach them either.
 *
 * WHAT EACH CHANGE DOES. ON raises ONE `history_enable` card and the route
 * answers "waiting" at once, so the page says so and re-reads the status while
 * it is waiting; OFF is immediate. Choosing a retention deletes conversations
 * older than the chosen age AT ONCE, so it asks here first and is held on a
 * stale link (rule 4) - turning history OFF is never held.
 *
 * @module chat-history-settings
 */

import { currentLink, linkWords } from "./jarvis-link.js";

const TAURI = globalThis.__TAURI__;
const IS_TAURI = Boolean(TAURI && TAURI.core && TAURI.core.invoke);

const $ = (id) => document.getElementById(id);

const el = {
  body: $("ch-body"),
  reading: $("ch-state"),
  sw: $("ch-switch"),
  keep: $("ch-keep"),
  note: $("ch-note"),
  line: $("ch-line"),
  linkNote: $("ch-link-note"),
  said: $("ch-status"),
};

const ASKING = "Asking the PC…";
const ON_BUTTON = "Turn chat history on";
const OFF_BUTTON = "Turn chat history off";
const WAITING_CARD =
  "Waiting for your approval card in the Jarvis bar. The switch stays off " +
  "until it is approved.";
const WAITING_LINK =
  "The connection is catching up. Turning chat history on, and changing how long it is " +
  "kept, wait for a live connection; turning it off works at once.";
const KEEP_CHOICES = [
  { days: 0, label: "Keep until I delete them" },
  { days: 30, label: "30 days" },
  { days: 90, label: "90 days" },
  { days: 365, label: "1 year" },
];

let view = null;
let busy = false;
let watch = null;

function live() {
  return linkWords(currentLink()).canAct;
}

function say(text, tone) {
  if (!el.said) return;
  el.said.textContent = text;
  if (tone) el.said.dataset.tone = tone;
  else delete el.said.dataset.tone;
}

function paintKeep() {
  if (!el.keep) return;
  el.keep.textContent = "";
  for (const choice of KEEP_CHOICES) {
    const option = document.createElement("option");
    option.value = String(choice.days);
    option.textContent = choice.label;
    el.keep.append(option);
  }
  if (view) el.keep.value = String(view.keep_days ?? 0);
}

function lineWords() {
  if (!view) return "";
  if (!view.enabled) {
    return "Chat history is off. Nothing new is kept; what was already kept stays until you delete it.";
  }
  if (view.recording === false) {
    const why = String(view.why_not || "").trim();
    return "Chat history is on, but the PC is not recording right now" + (why ? `: ${why}` : ".");
  }
  return "Chat history is on. Conversations are kept encrypted on this PC.";
}

function paint() {
  if (!el.body) return;
  el.reading.hidden = true;
  el.body.hidden = false;
  if (!view) {
    if (el.sw) el.sw.disabled = true;
    if (el.keep) el.keep.disabled = true;
    return;
  }
  // Turning it ON, or deleting older conversations by choosing a retention,
  // needs a live link; turning it OFF never waits.
  const held = !live() && view.enabled !== true;
  const keepHeld = !live();
  if (el.sw) {
    el.sw.disabled = busy || held;
    el.sw.textContent = view.enabled === true ? OFF_BUTTON : ON_BUTTON;
  }
  if (el.keep) {
    el.keep.disabled = busy || keepHeld;
    el.keep.value = String(view.keep_days ?? 0);
  }
  if (el.linkNote) {
    el.linkNote.textContent = (held || keepHeld) ? WAITING_LINK : "";
    el.linkNote.hidden = !(held || keepHeld);
  }
  if (el.line) el.line.textContent = lineWords();
  if (el.note && !el.note.textContent.trim()) {
    el.note.textContent =
      "This is where chat history is kept: the switch, and how long my chats are kept. " +
      "Choosing a shorter time deletes older conversations as soon as you choose it.";
  }
}

async function read() {
  const status = await TAURI.core.invoke("history_settings", { action: "read" });
  view = status;
  paint();
  return status;
}

async function load() {
  if (!el.body || !IS_TAURI) return;
  try {
    await read();
  } catch (error) {
    view = null;
    el.body.hidden = true;
    el.reading.hidden = false;
    el.reading.textContent = String((error && error.message) || error ||
      "The PC could not be asked about chat history.");
  }
}

/** A bounded re-read while an ON card waits; the page says it is waiting. */
function watchCard() {
  if (watch) clearInterval(watch);
  let tries = 0;
  watch = setInterval(async () => {
    tries += 1;
    try {
      const status = await read();
      if (status && status.enabled === true) {
        clearInterval(watch);
        watch = null;
        say("Chat history is on.", "ok");
      }
    } catch {
      // Keep waiting until the bound; the next paint says the PC could not be
      // asked, and the button stays available.
    }
    if (tries >= 10) {
      clearInterval(watch);
      watch = null;
    }
  }, 3000);
}

async function setSwitch(on) {
  if (busy) return;
  busy = true;
  say(on ? WAITING_CARD : ASKING);
  paint();
  try {
    const out = await TAURI.core.invoke("history_settings",
      { action: on ? "on" : "off" });
    if (out && out.waiting) {
      say((out && out.message) || WAITING_CARD, "warn");
      watchCard();
    } else {
      say((out && out.message) || (on ? "Chat history is on." : "Chat history is off."), "ok");
    }
  } catch (error) {
    say(String((error && error.message) || error), "warn");
  } finally {
    busy = false;
  }
  await load();
}

async function setKeep(days) {
  if (busy || !view) return;
  if (days === view.keep_days) return;
  const older = days === 0
    ? null
    : `Conversations older than ${KEEP_CHOICES.find((c) => c.days === days).label} ` +
      "deleted NOW. This cannot be undone.";
  if (older && !window.confirm(`${older}\n\nKeep chats for ${days === 365 ? "1 year" : days + " days"}?`)) {
    el.keep.value = String(view.keep_days ?? 0);
    return;
  }
  busy = true;
  say(ASKING);
  paint();
  try {
    const out = await TAURI.core.invoke("history_settings",
      { action: "keep", keepDays: days });
    say((out && out.message) || "Saved.", "ok");
    await read();
  } catch (error) {
    say(String((error && error.message) || error), "warn");
    if (view) el.keep.value = String(view.keep_days ?? 0);
  } finally {
    busy = false;
    paint();
  }
}

if (el.body && IS_TAURI) {
  paintKeep();
  el.sw?.addEventListener("click", () => setSwitch(!(view && view.enabled === true)));
  el.keep?.addEventListener("change", () => setKeep(Number(el.keep.value)));
  load();
} else if (el.reading) {
  el.reading.textContent = "This window cannot ask the PC.";
}
