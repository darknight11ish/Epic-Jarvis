/**
 * Settings -> "What asks first" (the owner's decisions of 2026-09-26, after
 * the approvals audit; JARVIS-API.md section 32; backend jarvis_asks_first.py,
 * asks-first.patch).
 *
 * Three Rust commands (src-tauri/src/asks_first.rs), Settings only:
 *  - get_asks_first: every action and whether it asks first, in the PC's
 *    words, grouped. A read.
 *  - set_asks_first {action, ask}: "Ask me first" on ONE action of the short
 *    safe list. ON (stricter) is immediate and never held. OFF (looser) is
 *    one approval card on the PC that needs Windows Hello, held on a stale
 *    link here (greyed) and in Rust. Rust refuses any other action, and so
 *    does the PC.
 *  - set_lights_without_card {enabled}: ON is one approval card (held on a
 *    stale link), OFF at once.
 *
 * The phone's Mind shows the same page (AsksFirstPlate.kt) in the same words
 * (net/AsksFirst.kt), with stricter switches only: loosening is the PC's.
 *
 * @module asks-first-settings
 */

import { announce, currentLink, linkWords, onLink, onQueue } from "./jarvis-link.js";
import {
  LIGHTS_DETAIL,
  LIGHTS_LABEL,
  lightsView,
  readAsksFirst,
  rowLine,
  STALE,
  SWITCH_LABEL,
  switchView,
} from "./asks-first.js";

const TAURI = globalThis.__TAURI__;
const IS_TAURI = Boolean(TAURI && TAURI.core && TAURI.core.invoke);
const $ = (id) => document.getElementById(id);

const el = {
  section: $("asks-first"),
  state: $("af-state"),
  body: $("af-body"),
  groups: $("af-groups"),
  status: $("af-status"),
};

let view = null;
let busy = false;

function node(tag, className, text) {
  const n = document.createElement(tag);
  if (className) n.className = className;
  if (text !== undefined) n.textContent = text;
  return n;
}

function live() {
  return linkWords(currentLink()).canAct;
}

/** An error in words, never a bridge error or JSON. */
function problemWords(error) {
  const said = String((error && error.message) || error || "").trim();
  if (!said || /[{}<>]|::|not allowed|undefined|null/i.test(said) || said.length > 400) {
    return "Could not ask Jarvis. Try again in a moment, or restart Jarvis Desktop.";
  }
  return said;
}

function say(text, tone) {
  if (!el.status) return;
  el.status.textContent = text;
  if (tone) el.status.dataset.tone = tone;
  else delete el.status.dataset.tone;
}

function toggle(id, label, detail, checked, disabled, onChange) {
  const wrap = node("label", "toggle");
  const box = node("input");
  box.type = "checkbox";
  box.id = id;
  box.checked = checked;
  box.disabled = disabled;
  box.addEventListener("change", (e) => onChange(e.target.checked, e.target));
  const words = node("span", "", label);
  if (detail) words.append(node("span", "toggle-detail", detail));
  wrap.append(box, words);
  return wrap;
}

function paintRow(row) {
  const li = node("li", "sc-gpu");
  li.dataset.asks = row.id;
  li.append(node("span", "sc-gpu-name", rowLine(row)));
  if (row.note) li.append(node("span", "sc-gpu-role", row.note));
  const sw = switchView(row, view, live());
  if (sw) {
    li.append(toggle(`af-${row.action}`, SWITCH_LABEL, "", sw.checked, busy || sw.disabled,
      (want, box) => change(row, want, box)));
    for (const line of sw.lines) li.append(node("span", "sc-gpu-role", line));
  }
  if (row.lights) {
    const lv = lightsView(view.lights, live());
    if (lv.show) {
      const t = toggle("af-lights", LIGHTS_LABEL, LIGHTS_DETAIL, lv.checked,
        busy || !lv.canChange, (want, box) => changeLights(want, box));
      if (!lv.canChange) t.title = STALE;
      li.append(t);
      for (const line of lv.lines) li.append(node("span", "sc-gpu-role", line));
    }
  }
  return li;
}

function paint() {
  if (!el.section || !view) return;
  if (!view.available) {
    el.state.textContent = view.why;
    el.body.hidden = true;
    return;
  }
  el.state.textContent = "";
  el.body.hidden = false;
  el.groups.replaceChildren(...view.groups.map((g) => {
    const box = node("div", "af-group");
    box.append(node("h3", "subhead", g.title));
    const ul = node("ul", "sc-cards");
    ul.append(...g.rows.map(paintRow));
    box.append(ul);
    return box;
  }));
}

async function load() {
  if (!el.section) return;
  if (!IS_TAURI) {
    el.state.textContent = "Open this in Jarvis Desktop to see what asks first.";
    return;
  }
  try {
    view = readAsksFirst(await TAURI.core.invoke("get_asks_first"));
  } catch (error) {
    el.state.textContent = problemWords(error);
    return;
  }
  paint();
}

/** "Ask me first": ON stricter at once; OFF looser, one card on the PC. */
async function change(row, ask, box) {
  if (busy) return;
  if (!ask && !live()) {
    box.checked = true;
    say(STALE, "bad");
    return;
  }
  busy = true;
  say(ask ? "Making it ask first…" : "Asking for your approval…");
  try {
    const out = await TAURI.core.invoke("set_asks_first", { action: row.action, ask });
    const words = String((out && (out.message || out.error)) || "Done.");
    say(words, out && out.ok === false ? "bad" : "ok");
    announce(words);
  } catch (error) {
    say(problemWords(error), "bad");
  } finally {
    busy = false;
  }
  await load();
}

/** The lights setting: ON one card (held on a stale link), OFF at once. */
async function changeLights(on, box) {
  if (busy) return;
  if (on && !live()) {
    box.checked = false;
    say(STALE, "bad");
    return;
  }
  busy = true;
  say(on ? "Asking…" : "Turning it off…");
  try {
    const out = await TAURI.core.invoke("set_lights_without_card", { enabled: on });
    const words = String((out && (out.message || out.error)) || "Done.");
    say(words, out && out.ok === false ? "bad" : "ok");
    announce(words);
  } catch (error) {
    say(problemWords(error), "bad");
  } finally {
    busy = false;
  }
  await load();
}

onLink(() => paint());
// A card answered (or expired): a tier or the lights setting may have
// changed. onQueue also delivers the current queue at once - the first read.
onQueue(() => load());
document.addEventListener("visibilitychange", () => {
  if (!document.hidden) load();
});
