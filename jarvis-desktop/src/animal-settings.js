/**
 * Settings -> "Animal options" -> "Shared with your phone" (the owner's
 * decisions of 2026-09-28; JARVIS-API.md section 60).
 *
 * "Keep the animal still" and the animal's behaviour switches, kept on the
 * PC (backend/jarvis_animal.py) so a change here, on the phone or by asking
 * Jarvis changes both. Two Rust commands (src-tauri/src/animal.rs),
 * Settings only:
 *  - get_animal: every switch with its value and the PC's own words;
 *  - set_animal {change}: ONE switch. Cosmetic, so no card either way;
 *    turning one ON waits for a live link (greyed here, held in Rust), OFF
 *    never does. Every face page on this computer changes at once
 *    (animal.rs re-reads the appearance document; jarvis-link.js keeps the
 *    values for the face frames, animal-shared.js).
 *
 * The rows are drawn from whatever the PC lists, so a new behaviour needs
 * no change here. On a PC too old to share them, only "Keep the animal
 * still" is offered, kept on this computer (face-tuning.js), and the line
 * says so.
 *
 * The rest of the section is other modules' as before: the sun, moon and
 * weather (sky-settings.js) and sharpness and frame rate on this computer
 * (settings.js with face-tuning.js). This module also gives the section its
 * way to the animal's voice.
 *
 * @module animal-settings
 */

import { announce, currentLink, linkWords, onLink } from "./jarvis-link.js";
import { SWITCHES, WORDS, storeAnimal } from "./animal-shared.js";
import { loadFaceTuning, saveFaceTuning } from "./face-tuning.js";

const TAURI = globalThis.__TAURI__;
const IS_TAURI = Boolean(TAURI && TAURI.core && TAURI.core.invoke);
const $ = (id) => document.getElementById(id);

const STALE = "Waiting for the link to catch up. Nothing can be turned on until it does.";
/** The line under the one switch an older PC leaves (this computer only). */
export const LOCAL_ONLY = "Kept on this computer only until your PC's Jarvis is updated.";

const el = {
  box: $("animal-options"),
  sharedNote: $("animal-shared-note"),
  state: $("animal-state"),
  list: $("animal-switches"),
  serious: $("animal-serious-note"),
  status: $("animal-status"),
  voiceGo: $("animal-voice-go"),
};

let view = null;
let busy = false;

function say(target, text, tone) {
  if (!target) return;
  target.textContent = text || "";
  if (tone) target.dataset.tone = tone;
  else delete target.dataset.tone;
}

function problemWords(error) {
  const said = String((error && error.message) || error || "").trim();
  if (!said || /[{}<>]|::|not allowed|undefined|null/i.test(said) || said.length > 600) {
    return "Try again in a moment, or restart Jarvis Desktop.";
  }
  return said;
}

function syncButtons() {
  if (!el.list) return;
  const live = linkWords(currentLink()).canAct;
  for (const box of el.list.querySelectorAll("input[type=checkbox]")) {
    if (box.dataset.local === "true") { box.disabled = false; continue; }
    // Turning something on waits for the link; turning it off never does.
    const adds = !box.checked;
    box.disabled = busy || (adds && !live);
    box.title = adds && !live ? STALE : "";
  }
}

function row(sw, on, { local = false, coming = "" } = {}) {
  const label = document.createElement("label");
  label.className = "toggle";
  label.dataset.animal = sw.id;
  const box = document.createElement("input");
  box.type = "checkbox";
  box.id = `animal-${sw.id}`;
  box.checked = on === true;
  if (local) box.dataset.local = "true";
  box.addEventListener("change", () => (local ? saveLocalStill(box.checked) : change(sw.id, box.checked, box)));
  const text = document.createElement("span");
  text.append(sw.label);
  const detail = document.createElement("span");
  detail.className = "toggle-detail";
  detail.textContent = [sw.detail, sw.built === false ? coming : "", local ? LOCAL_ONLY : ""]
    .filter(Boolean).join(" ");
  text.append(detail);
  label.append(box, text);
  return label;
}

function paint() {
  if (!el.box || !el.list) return;
  const v = view || {};
  el.list.replaceChildren();
  if (v.available === false || !Array.isArray(v.switches)) {
    // An older PC: nothing is shared yet. "Keep the animal still" stays
    // usable on this computer, as it was before.
    say(el.state, v.why || WORDS.missing);
    say(el.sharedNote, "");
    say(el.serious, "");
    const still = SWITCHES.find((s) => s.id === "still");
    el.list.append(row(still, loadFaceTuning().still === true, { local: true }));
    syncButtons();
    return;
  }
  say(el.state, "");
  say(el.sharedNote, v.shared_note || WORDS.shared_note);
  say(el.serious, v.serious_note || WORDS.serious_note);
  for (const sw of v.switches) {
    if (!sw || typeof sw.id !== "string") continue;
    el.list.append(row(sw, sw.on, { coming: v.coming || WORDS.coming }));
  }
  syncButtons();
}

function saveLocalStill(on) {
  saveFaceTuning({ ...loadFaceTuning(), still: on });
  const said = on ? "Saved on this computer. The animal will keep still."
    : "Saved on this computer. The animal moves as usual.";
  say(el.status, said, "ok");
  announce(said);
}

async function load() {
  if (!el.box || !IS_TAURI) return;
  try {
    const got = await TAURI.core.invoke("get_animal");
    view = got && typeof got === "object" ? got : { available: false, why: WORDS.missing };
  } catch (error) {
    say(el.state, `Could not read them: ${problemWords(error)}`, "bad");
    return;
  }
  if (view.available !== false && view.values) storeAnimal(view.values);
  paint();
}

async function change(id, on, box) {
  if (busy) {
    box.checked = !on;
    return;
  }
  busy = true;
  syncButtons();
  say(el.status, "Sending…");
  try {
    const out = await TAURI.core.invoke("set_animal", { change: { [id]: on } });
    const said = String((out && (out.said || out.error)) || "Done.");
    say(el.status, said, out && out.ok === false ? "bad" : "ok");
    announce(said);
    if (out && out.view) {
      view = out.view;
      if (view.values) storeAnimal(view.values);
    }
  } catch (error) {
    say(el.status, problemWords(error), "bad");
    announce(el.status.textContent, "assertive");
  } finally {
    busy = false;
  }
  await load();
}

/** "Go to the animal's voice": the Jarvis's voice card, at "Voice follows the face". */
function goToVoice() {
  const target = $("cv-face") && !$("cv-face").hidden ? $("cv-face") : $("voices");
  if (!target) return;
  target.scrollIntoView({ block: "start" });
  const focusable = $("cv-face-switch") && !$("cv-face").hidden ? $("cv-face-switch") : target;
  if (focusable === target && !target.hasAttribute("tabindex")) target.setAttribute("tabindex", "-1");
  focusable.focus({ preventScroll: true });
}

if (el.box) {
  if (el.voiceGo) el.voiceGo.addEventListener("click", goToVoice);
  onLink(() => syncButtons());
  load();
  // A change made on the phone or by asking Jarvis: the PC rings the
  // appearance doorbell, and every window hears it as appearance-changed.
  if (IS_TAURI && TAURI.event && TAURI.event.listen) {
    TAURI.event.listen("appearance-changed", () => { if (!busy) load(); });
  }
  document.addEventListener("visibilitychange", () => {
    if (!document.hidden) load();
  });
}
