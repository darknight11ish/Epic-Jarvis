/**
 * Settings -> Web search (the owner's decisions of 2026-09-25; JARVIS-API.md
 * section 23; backend jarvis_search.py, web-search.patch).
 *
 * Rust commands (src-tauri/src/web_search.rs), Settings only:
 *  - get_web_search: the five providers with the PC's own "why use this one"
 *    lines, which is chosen, whether each is ready, the SearXNG address,
 *    "Ask before every web search", and Whoogle's reason for being left out;
 *  - set_web_search: ONE change - the provider or the address at once, "Ask
 *    before every web search" on at once, off through ONE approval card on
 *    the PC. Held on a stale link, here (greyed) and in Rust;
 *  - test_web_search: one search for a fixed word through the chosen
 *    provider, and what happened in plain words. Held on a stale link too;
 *  - save_search_key / forget_search_key: the Exa, Tavily or Brave Search key,
 *    straight into Credential Manager on this PC. The box is emptied as soon
 *    as it is sent, and the key is never shown again - only whether one is
 *    saved. The phone has no such box (ARCHITECTURE.md section 8).
 *
 * The phone's Mind -> Web search does the rest the same (WebSearchPlate.kt),
 * in the same words (net/WebSearch.kt).
 *
 * @module web-search-settings
 */

import { announce, currentLink, linkWords, onLink, onQueue } from "./jarvis-link.js";
import {
  ADDRESS_LABEL,
  ADDRESS_NOTE,
  ADDRESS_SAVE,
  KEY_FORGET,
  KEY_SAVE,
  KEYED,
  keyLine,
  LEFT_OUT_TITLE,
  providerLine,
  readSearch,
  TEST_BUSY,
  TEST_LABEL,
  TEST_NOTE,
  testWords,
} from "./web-search.js";

const TAURI = globalThis.__TAURI__;
const IS_TAURI = Boolean(TAURI && TAURI.core && TAURI.core.invoke);
const $ = (id) => document.getElementById(id);

async function invoke(command, args = {}) {
  if (!IS_TAURI) throw new Error("no desktop backend");
  return TAURI.core.invoke(command, args);
}

const ws = {
  section: $("web-search"),
  state: $("ws-state"),
  body: $("ws-body"),
  providers: $("ws-providers"),
  leftOutTitle: $("ws-left-out-title"),
  leftOut: $("ws-left-out"),
  defaultWhy: $("ws-default-why"),
  why: $("ws-why"),
  addressLabel: $("ws-address-label"),
  address: $("ws-address"),
  addressNote: $("ws-address-note"),
  addressSave: $("ws-address-save"),
  keyEntry: $("ws-key-entry"),
  keys: $("ws-keys"),
  ask: $("ws-ask"),
  askLabel: $("ws-ask-label"),
  askDetail: $("ws-ask-detail"),
  askStatus: $("ws-ask-status"),
  test: $("ws-test"),
  testNote: $("ws-test-note"),
  testStatus: $("ws-test-status"),
  status: $("ws-status"),
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

function canAct() {
  return linkWords(currentLink()).canAct;
}

/** Changes sent to the PC are greyed on a stale link; the key boxes are not
 *  (a key goes into this PC's Credential Manager, not over the link). */
function syncButtons() {
  const live = canAct();
  if (!ws.section) return;
  for (const el of ws.section.querySelectorAll("[data-live]")) {
    el.disabled = busy || !live;
    el.title = live ? "" : STALE;
  }
  for (const el of ws.section.querySelectorAll("[data-local]")) el.disabled = busy;
}

function paintProviders() {
  ws.providers.replaceChildren();
  for (const p of view.providers) {
    const row = node("label", "theme-row");
    row.dataset.choice = p.id;
    const radio = document.createElement("input");
    radio.type = "radio";
    radio.name = "ws-provider";
    radio.value = p.id;
    radio.checked = p.id === view.provider;
    radio.dataset.live = "true";
    radio.addEventListener("change", () => {
      if (radio.checked) change({ provider: p.id });
    });
    const text = node("span", "theme-text");
    text.append(node("span", "theme-name", p.label));
    text.append(node("span", "theme-blurb", p.why));
    const line = node("span", "theme-blurb", providerLine(p, view.provider));
    line.dataset.state = p.ready ? "ready" : p.state || "";
    text.append(line);
    const tick = node("span", "theme-check", "✓");
    tick.setAttribute("aria-hidden", "true");
    row.append(radio, text, tick);
    ws.providers.append(row);
  }
}

function paintKeys() {
  ws.keys.replaceChildren();
  for (const p of view.providers.filter((x) => KEYED.includes(x.id))) {
    const box = node("div", "sc-switch");
    box.dataset.key = p.id;
    const label = node("label", "label", `${p.label} key`);
    const id = `ws-key-${p.id}`;
    label.htmlFor = id;
    const row = node("div", "row sc-command");
    const input = document.createElement("input");
    input.type = "password";
    input.id = id;
    input.autocomplete = "off";
    input.spellcheck = false;
    input.placeholder = `Paste your ${p.label} key`;
    const save = node("button", "btn small", KEY_SAVE);
    save.type = "button";
    save.dataset.local = "true";
    save.addEventListener("click", () => saveKey(p, input));
    const forget = node("button", "btn ghost small", KEY_FORGET);
    forget.type = "button";
    forget.dataset.local = "true";
    forget.hidden = p.keySaved !== true;
    forget.addEventListener("click", () => forgetKey(p));
    row.append(input, save, forget);
    box.append(label, row);
    box.append(node("p", "sc-line", keyLine(p)));
    box.append(node("p", "note", `Get one at ${p.keyWhere}.`));
    ws.keys.append(box);
  }
}

function paint() {
  if (!ws.section || !view) return;
  if (!view.available) {
    say(ws.state, view.why);
    ws.body.hidden = true;
    return;
  }
  ws.state.textContent = "";
  ws.body.hidden = false;
  paintProviders();
  if (ws.leftOutTitle) ws.leftOutTitle.textContent = LEFT_OUT_TITLE;
  ws.leftOut.replaceChildren(...view.leftOut.map((x) => {
    const li = node("li", "sc-gpu");
    li.append(node("span", "sc-gpu-name", x.label), node("span", "sc-gpu-role", x.why));
    return li;
  }));
  say(ws.defaultWhy, view.defaultWhy);
  say(ws.why, view.why, view.why ? "bad" : null);
  if (ws.addressLabel) ws.addressLabel.textContent = ADDRESS_LABEL;
  if (document.activeElement !== ws.address) ws.address.value = view.address;
  say(ws.addressNote, ADDRESS_NOTE);
  ws.addressSave.textContent = ADDRESS_SAVE;
  ws.addressSave.dataset.live = "true";
  say(ws.keyEntry, view.keyEntry);
  paintKeys();
  ws.ask.checked = view.askEveryTime;
  ws.ask.dataset.live = "true";
  ws.askLabel.textContent = view.askLabel;
  ws.askDetail.textContent = view.askDetail;
  say(ws.askStatus, view.waiting ? "Waiting for your approval card." : view.last);
  ws.test.textContent = TEST_LABEL;
  ws.test.dataset.live = "true";
  say(ws.testNote, TEST_NOTE);
  syncButtons();
}

async function load() {
  if (!ws.section || !IS_TAURI) return;
  try {
    view = readSearch(await invoke("get_web_search"));
  } catch (error) {
    say(ws.state, `Could not read it: ${problemWords(error)}`, "bad");
    return;
  }
  paint();
}

async function change(args) {
  if (busy) return;
  busy = true;
  syncButtons();
  say(ws.status, "Sending…");
  try {
    const out = await invoke("set_web_search", args);
    const said = String((out && (out.said || out.error)) || "Done.");
    say(ws.status, said, out && out.ok === false ? "bad" : "ok");
    announce(said);
  } catch (error) {
    say(ws.status, problemWords(error), "bad");
    announce(ws.status.textContent, "assertive");
  } finally {
    busy = false;
  }
  await load();
}

async function saveKey(p, input) {
  if (busy) return;
  const key = input.value;
  // Emptied at once: the key is not kept in the page a moment longer than
  // the one call that saves it.
  input.value = "";
  if (!key.trim()) {
    say(ws.status, "Paste the key first.", "bad");
    return;
  }
  busy = true;
  syncButtons();
  try {
    const out = await invoke("save_search_key", { provider: p.id, key });
    say(ws.status, String((out && out.said) || "Saved."), "ok");
  } catch (error) {
    say(ws.status, problemWords(error), "bad");
  } finally {
    busy = false;
  }
  await load();
}

async function forgetKey(p) {
  if (busy) return;
  busy = true;
  syncButtons();
  try {
    const out = await invoke("forget_search_key", { provider: p.id });
    say(ws.status, String((out && out.said) || "Removed."), "ok");
  } catch (error) {
    say(ws.status, problemWords(error), "bad");
  } finally {
    busy = false;
  }
  await load();
}

async function runTest() {
  if (busy) return;
  busy = true;
  syncButtons();
  say(ws.testStatus, TEST_BUSY);
  try {
    const out = testWords(await invoke("test_web_search"));
    say(ws.testStatus, out.text, out.tone);
    announce(out.text);
  } catch (error) {
    say(ws.testStatus, problemWords(error), "bad");
  } finally {
    busy = false;
    syncButtons();
  }
}

if (ws.section) {
  ws.addressSave.addEventListener("click", () => change({ searxngUrl: ws.address.value }));
  ws.ask.addEventListener("change", () => {
    const on = ws.ask.checked;
    // Shown as it really is until the PC says otherwise: turning it off
    // waits for a card, so the box does not claim "off" before that.
    if (view) ws.ask.checked = view.askEveryTime;
    change({ askEveryTime: on });
  });
  ws.test.addEventListener("click", runTest);
}
onLink(() => syncButtons());
// A card answered (or expired): "Ask before every web search" may have
// changed. onQueue also delivers the current queue at once - the first read.
onQueue(() => load());
document.addEventListener("visibilitychange", () => {
  if (!document.hidden) load();
});
