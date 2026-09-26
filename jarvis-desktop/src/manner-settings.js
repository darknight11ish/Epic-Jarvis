/**
 * Settings -> "How Jarvis talks": warm and brief, or plain (the owner's
 * decision of 2026-09-25; JARVIS-API.md section 27).
 *
 * Two Rust commands (src-tauri/src/plain_errors.rs), Settings only:
 *  - get_manner: the choice, with the PC's own words for both;
 *  - set_manner {manner}: at once, NO approval card either way - it changes
 *    only how answers are worded. Held on a stale link, here (greyed) and
 *    in Rust, like every change sent to the PC.
 *
 * The phone's Mind -> "How Jarvis talks" does the same (MannerPlate.kt), in
 * the same words (manner.js, net/Manner.kt).
 *
 * @module manner-settings
 */

import { announce, currentLink, linkWords, onLink } from "./jarvis-link.js";
import { readManner, SAID } from "./manner.js";

const TAURI = globalThis.__TAURI__;
const IS_TAURI = Boolean(TAURI && TAURI.core && TAURI.core.invoke);
const $ = (id) => document.getElementById(id);

async function invoke(command, args = {}) {
  if (!IS_TAURI) throw new Error("no desktop backend");
  return TAURI.core.invoke(command, args);
}

const mn = {
  section: $("manner"),
  state: $("mn-state"),
  body: $("mn-body"),
  detail: $("mn-detail"),
  choices: $("mn-choices"),
  spoken: $("mn-spoken"),
  status: $("mn-status"),
};

const STALE = "Waiting for the link to catch up. Nothing can be sent until it does.";

let view = null;
let busy = false;

function node(tag, className, text) {
  const n = document.createElement(tag);
  if (className) n.className = className;
  if (text !== undefined) n.textContent = text;
  return n;
}

function say(target, text, tone) {
  if (!target) return;
  target.textContent = text;
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

function syncButtons() {
  if (!mn.section) return;
  const live = linkWords(currentLink()).canAct;
  for (const el of mn.section.querySelectorAll("[data-live]")) {
    el.disabled = busy || !live;
    el.title = live ? "" : STALE;
  }
}

function paint() {
  if (!mn.section || !view) return;
  if (!view.available) {
    say(mn.state, view.why);
    mn.body.hidden = true;
    return;
  }
  mn.state.textContent = "";
  mn.body.hidden = false;
  say(mn.detail, view.detail);
  mn.choices.replaceChildren();
  for (const c of view.choices) {
    const row = node("label", "theme-row");
    row.dataset.choice = c.id;
    const radio = document.createElement("input");
    radio.type = "radio";
    radio.name = "mn-manner";
    radio.value = c.id;
    radio.checked = c.id === view.manner;
    radio.dataset.live = "true";
    radio.addEventListener("change", () => {
      if (radio.checked) change(c.id);
    });
    const text = node("span", "theme-text");
    text.append(node("span", "theme-name", c.label), node("span", "theme-blurb", c.why));
    const tick = node("span", "theme-check", "✓");
    tick.setAttribute("aria-hidden", "true");
    row.append(radio, text, tick);
    mn.choices.append(row);
  }
  say(mn.spoken, view.spoken);
  syncButtons();
}

async function load() {
  if (!mn.section || !IS_TAURI) return;
  try {
    view = readManner(await invoke("get_manner"));
  } catch (error) {
    say(mn.state, `Could not read it: ${problemWords(error)}`, "bad");
    return;
  }
  paint();
}

async function change(manner) {
  if (busy) return;
  busy = true;
  syncButtons();
  say(mn.status, "Sending…");
  try {
    const out = await invoke("set_manner", { manner });
    const said = String((out && (out.said || out.error)) || SAID[manner] || "Done.");
    say(mn.status, said, out && out.ok === false ? "bad" : "ok");
    announce(said);
  } catch (error) {
    say(mn.status, problemWords(error), "bad");
    announce(mn.status.textContent, "assertive");
  } finally {
    busy = false;
  }
  await load();
}

onLink(() => syncButtons());
load();
document.addEventListener("visibilitychange", () => {
  if (!document.hidden) load();
});
