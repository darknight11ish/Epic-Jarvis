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

import { announce, currentLink, linkWords, onEvent, onLink, onQueue } from "./jarvis-link.js";
import {
  LIGHTS_DETAIL,
  LIGHTS_LABEL,
  LOCKDOWN_ACTION,
  LOCKDOWN_DETAIL,
  LOCKDOWN_LABEL,
  lockdownView,
  lightsView,
  readAsksFirst,
  rowLine,
  STALE,
  SWITCH_LABEL,
  switchView,
  TOOLS_DETAIL,
  TOOLS_LABEL,
  notOfferedView,
  toolGroupsView,
  toolSwitchView,
  vaultSwitchView,
} from "./asks-first.js";

const TAURI = globalThis.__TAURI__;
const IS_TAURI = Boolean(TAURI && TAURI.core && TAURI.core.invoke);
const $ = (id) => document.getElementById(id);

const el = {
  section: $("asks-first"),
  state: $("af-state"),
  body: $("af-body"),
  groups: $("af-groups"),
  tools: $("af-tools"),
  lockdown: $("af-lockdown"),
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
  paintLockdown();
  el.groups.replaceChildren(...view.groups.map((g) => {
    const box = node("div", "af-group");
    box.append(node("h3", "subhead", g.title));
    const ul = node("ul", "sc-cards");
    ul.append(...g.rows.map(paintRow));
    box.append(ul);
    return box;
  }));
  paintTools();
}

/**
 * "Let the AI use this": the tiered one-tool switches (Tier A and Tier B),
 * grouped, plus the vault organizer's own separate row, plus the plain note
 * naming every tool this slice does NOT offer in-app. One switch per row;
 * phone read-only because can_enable is false there.
 */
function paintTools() {
  if (!el.tools) return;
  const tools = view.tools;
  if (!tools || !tools.items.length) {
    el.tools.replaceChildren();
    return;
  }
  const parts = [node("h3", "subhead", TOOLS_LABEL),
    node("p", "note", tools.detail || TOOLS_DETAIL)];
  for (const group of toolGroupsView(tools)) {
    const box = node("div", "af-group");
    box.append(node("h4", "subhead", group.title));
    const ul = node("ul", "sc-cards");
    for (const item of group.items) {
      const li = node("li", "sc-gpu");
      li.dataset.tool = item.id;
      li.append(node("span", "sc-gpu-name", item.title));
      const tv = toolSwitchView(item, tools, live());
      if (tv) {
        li.append(toggle(`af-tool-${item.id}`, TOOLS_LABEL, "", tv.checked,
          busy || tv.disabled, (want, box2) => changeTool(item.id, want, box2)));
        for (const line of tv.lines) li.append(node("span", "sc-gpu-role", line));
      }
      ul.append(li);
    }
    box.append(ul);
    parts.push(box);
  }
  if (tools.vault) {
    const li = node("li", "sc-gpu");
    li.dataset.tool = tools.vault.id;
    li.append(node("span", "sc-gpu-name", tools.vault.title));
    const vv = vaultSwitchView(tools.vault, live());
    if (vv) {
      li.append(toggle("af-vault-organizer", TOOLS_LABEL, "", vv.checked,
        busy || vv.disabled, (want, box2) => changeVault(want, box2)));
      for (const line of vv.lines) li.append(node("span", "sc-gpu-role", line));
    }
    const ul = node("ul", "sc-cards");
    ul.append(li);
    parts.push(node("h4", "subhead", "Its own switch"), ul);
  }
  const note = notOfferedView(tools);
  if (note) parts.push(node("p", "note", note));
  el.tools.replaceChildren(...parts);
}

/**
 * Lockdown, at the top of the page (2026-09-28): what it is, whether it is
 * on, and ONE button - on at once, or (on the PC) off through one card that
 * needs Windows Hello.
 */
function paintLockdown() {
  if (!el.lockdown) return;
  const lv = lockdownView(view.lockdown, live());
  el.lockdown.hidden = !lv.show;
  if (!lv.show) {
    el.lockdown.replaceChildren();
    return;
  }
  el.lockdown.dataset.on = lv.on ? "true" : "false";
  const head = node("h3", "subhead", LOCKDOWN_LABEL);
  const detail = node("p", "note", LOCKDOWN_DETAIL);
  const lines = lv.lines.map((l, i) => node(i === 0 ? "strong" : "span",
    i === 0 ? "af-lockdown-state" : "sc-gpu-role", l));
  const parts = [head, detail, ...lines];
  if (lv.button) {
    const b = node("button", "btn small", lv.button.label);
    b.type = "button";
    b.id = "af-lockdown-button";
    b.disabled = busy || lv.button.disabled;
    b.addEventListener("click", () => changeLockdown(lv.button.ask));
    parts.push(b);
  }
  el.lockdown.replaceChildren(...parts);
}

/** Lockdown ON at once (never held); OFF one card on the PC (held on a stale link). */
async function changeLockdown(ask) {
  if (busy) return;
  if (!ask && !live()) {
    say(STALE, "bad");
    return;
  }
  busy = true;
  paint();
  say(ask ? "Turning on Lockdown…" : "Asking for your approval…");
  try {
    const out = await TAURI.core.invoke("set_asks_first", { action: LOCKDOWN_ACTION, ask });
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

/**
 * "Let the AI use this", on every Tier A/Tier B tool: ON one card (held on a
 * stale link, Windows Hello on the PC), OFF at once.
 */
async function changeTool(tool, enabled, box) {
  if (busy) return;
  if (enabled && !live()) {
    box.checked = false;
    say(STALE, "bad");
    return;
  }
  busy = true;
  say(enabled ? "Asking…" : "Turning it off…");
  try {
    const out = await TAURI.core.invoke("set_tool_enabled", { tool, enabled });
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

/**
 * The vault organizer's own switch: ON one card + Windows Hello on the PC,
 * OFF at once. A separate route from the tool switches; the page says so.
 */
async function changeVault(enabled, box) {
  if (busy) return;
  if (enabled && !live()) {
    box.checked = false;
    say(STALE, "bad");
    return;
  }
  busy = true;
  say(enabled ? "Asking…" : "Turning it off…");
  try {
    const out = await TAURI.core.invoke("set_vault_organizer_enabled", { enabled });
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
// Lockdown turned on or off - from the phone, by voice, or its card decided.
onEvent((frame) => {
  if (frame && frame.kind === "lockdown") load();
});
