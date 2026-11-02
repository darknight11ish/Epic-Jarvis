/**
 * Settings -> "To-do list carry-over" (2026-11-02; the owner's choice of both
 * modes, full daily rollover as the default; Gemini's ruling 8;
 * backend/jarvis_schedule.py; docs/JARVIS-API.md section 179).
 *
 * ONE Rust command (`src-tauri/src/todo_carryover.rs` `todo_carryover`),
 * Settings only, with two shapes:
 *  - no `mode`:  read the mode in force and the two modes in the PC's own
 *                words (GET /api/schedule's `todo_mode` and `todo_modes`).
 *  - `{ mode }`: change it (POST /api/schedule/act {"do": "todo_mode",
 *                "mode": ...}), held on a stale link.
 *
 * NO APPROVAL CARD EITHER WAY, and the PC decides that, not this page: the
 * change moves no item, deletes nothing, re-stamps no day and loosens no rule -
 * it only changes how the owner's own list is drawn. `created_date` is written
 * once when an item is created, so switching back and forth loses nothing.
 *
 * The buttons are BUILT FROM THE PC'S ANSWER (its labels and its details), so
 * this page cannot invent a third mode or rename one. A spoken sentence runs
 * the SAME method through the settings registry
 * (`jarvis_settings_registry.set_todo_carryover`), so a tap here and "set the
 * to-do list mode to day by day" cannot disagree.
 *
 * @module todo-carryover-settings
 */

import { currentLink, linkWords } from "./jarvis-link.js";

const TAURI = globalThis.__TAURI__;
const IS_TAURI = Boolean(TAURI && TAURI.core && TAURI.core.invoke);

const $ = (id) => document.getElementById(id);

const el = {
  section: $("todo-carryover"),
  choices: $("tc-choices"),
  status: $("tc-status"),
};

const ASKING = "Asking the PC…";
const STALE = "The connection is catching up. Try again in a moment - nothing was changed.";

let view = null;
let busy = false;

function live() {
  return linkWords(currentLink()).canAct;
}

function say(text, tone) {
  if (!el.status) return;
  el.status.textContent = text;
  if (tone) el.status.dataset.tone = tone;
  else delete el.status.dataset.tone;
}

function node(tag, className, text) {
  const n = document.createElement(tag);
  if (className) n.className = className;
  if (text !== undefined) n.textContent = text;
  return n;
}

/** One mode's row: the label the PC gave it, and its own one-line detail. */
export function modeRow(mode, chosen, onPick) {
  const label = node("label", "theme-row");
  const input = node("input");
  input.type = "radio";
  input.name = "tc-mode";
  input.value = mode.value;
  input.checked = Boolean(chosen);
  input.addEventListener("change", () => {
    if (input.checked) onPick(mode.value);
  });
  const words = node("span", "theme-words");
  words.append(node("span", "theme-title", mode.label || mode.value));
  if (mode.detail) words.append(node("span", "theme-note", mode.detail));
  label.append(input, words);
  return label;
}

export function paint() {
  if (!el.choices) return;
  if (!view) {
    el.choices.replaceChildren(node("p", "empty", ASKING));
    return;
  }
  const modes = Array.isArray(view.modes) && view.modes.length ? view.modes : [
    { value: "rollover", label: "Daily rollover", detail: "" },
    { value: "day", label: "Day by day", detail: "" },
  ];
  const rows = modes.map((m) => modeRow(m, m.value === view.mode, pick));
  for (const r of rows) {
    const input = r.querySelector("input");
    if (input) input.disabled = busy || !IS_TAURI;
  }
  el.choices.replaceChildren(...rows);
}

async function read() {
  if (!IS_TAURI) {
    say("This page needs the Jarvis app to reach your PC.");
    paint();
    return;
  }
  try {
    view = await TAURI.core.invoke("todo_carryover");
    say("");
  } catch (error) {
    view = null;
    say(String((error && error.message) || error || "Could not read it."), "bad");
  }
  paint();
}

async function pick(mode) {
  if (busy || !IS_TAURI || !view || mode === view.mode) return;
  if (!live()) {
    say(STALE, "bad");
    paint();
    return;
  }
  busy = true;
  paint();
  try {
    const out = await TAURI.core.invoke("todo_carryover", { mode });
    // The PC's own sentence says what happened, and its answer carries the
    // mode now in force - never this page's guess at it.
    say(String((out && (out.said || out.message)) || "Saved."), "ok");
    await read();
  } catch (error) {
    say(String((error && error.message) || error || "That did not work."), "bad");
  } finally {
    busy = false;
    paint();
  }
}

if (el.section) read();
