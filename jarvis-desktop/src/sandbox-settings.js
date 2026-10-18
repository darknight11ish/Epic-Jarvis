/**
 * Settings -> "Data and maths sandbox" (LM-1C, 2026-10-18;
 * backend/jarvis_sandbox_exec.py, the drop-in folder
 * plugins/ready/sandbox/, and the route GET/POST /api/sandbox it installs).
 *
 * One Rust command (src-tauri/src/sandbox_exec.rs `sandbox_exec`), Settings
 * only:
 *  - read: the switch and the PC's own line about it (on, off, a card
 *    waiting, or what the last card did - denied, timed out, refused).
 *  - on:   ONE normal approval card on the PC, decided in the Jarvis bar;
 *    nothing changes before a person says yes. Held on a stale link.
 *  - off:  at once, and never held.
 *
 * The page never runs a script and never sees a file or a piece of data: the
 * sandbox runs on the PC, and this is a switch position plus the PC's words.
 *
 * @module sandbox-settings
 */

import { currentLink, linkWords, onLink } from "./jarvis-link.js";
import {
  ASKING,
  COULD_NOT_TURN_ON,
  WAITING_LINK,
  refusedWords,
  sandboxView,
} from "./sandbox-rules.js";

const TAURI = globalThis.__TAURI__;
const IS_TAURI = Boolean(TAURI && TAURI.core && TAURI.core.invoke);
const $ = (id) => document.getElementById(id);

const el = {
  body: $("sbx-body"),
  reading: $("sbx-reading"),
  sw: $("sbx-switch"),
  linkNote: $("sbx-link-note"),
  line: $("sbx-line"),
  state: $("sbx-state"),
  say: $("sbx-status"),
};

let view = null;
let busy = false;
let poll = null;

function live() {
  return linkWords(currentLink()).canAct;
}

function say(text, tone) {
  if (!el.say) return;
  el.say.textContent = text;
  if (tone) el.say.dataset.tone = tone;
  else delete el.say.dataset.tone;
}

function paint() {
  if (!el.body) return;
  el.reading.hidden = true;
  el.body.hidden = false;
  if (!view) {
    el.sw.indeterminate = true;
    el.sw.disabled = true;
    return;
  }
  el.sw.indeterminate = false;
  el.sw.checked = view.checked;
  // Turning it ON needs a live link (a card is raised); turning it OFF never
  // waits (rule 4 only holds what loosens). While a card waits the switch stays
  // usable, so it can be turned back off (which takes the request back).
  const held = !view.checked && !live();
  el.sw.disabled = busy || held;
  el.linkNote.textContent = held ? WAITING_LINK : "";
  el.linkNote.hidden = !held;
  el.line.textContent = view.line;
  el.state.textContent = view.status && view.status !== view.line ? view.status : "";
  el.state.hidden = !el.state.textContent;
}

async function load() {
  if (!el.body || !IS_TAURI) return;
  clearTimeout(poll);
  try {
    const raw = await TAURI.core.invoke("sandbox_exec", { action: "read" });
    view = sandboxView(raw);
  } catch (error) {
    // An older PC, or a read that failed while it may well be ON: say the
    // PC's reason and do NOT show the switch as off (that would be a claim).
    view = null;
    el.body.hidden = true;
    el.reading.hidden = false;
    el.reading.textContent = refusedWords(error);
    return;
  }
  paint();
  // While a card waits, look again now and then so the switch follows the
  // answer, and so the line says what the card really did.
  poll = setTimeout(load, view && view.waiting ? 3000 : 15000);
}

async function setSwitch(on) {
  if (busy) return;
  busy = true;
  say(ASKING);
  paint();
  try {
    const out = await TAURI.core.invoke("sandbox_exec", {
      action: on ? "on" : "off",
    });
    const said = out && typeof out.message === "string" ? out.message : "";
    say(said, "ok");
  } catch (error) {
    say((on ? COULD_NOT_TURN_ON : "") + refusedWords(error), "warn");
  } finally {
    busy = false;
  }
  await load();
}

if (el.body) {
  el.reading.hidden = false;
  el.sw.addEventListener("change", (event) => setSwitch(event.target.checked));
  onLink(() => paint());
  load();
}
