/**
 * Settings -> Accounts (ease-of-use audit row 15, "Security G3" and the
 * owner's decision of 2026-10-06; JARVIS-API.md section 44; backend
 * jarvis_token_store.resolve_secret, jarvis_email.py, jarvis_calendar.py,
 * jarvis_home.py, jarvis_accounts.py).
 *
 * TWO GROUPS OF COMMANDS, Settings only, one for each shape:
 *
 *  - get_account_secrets / save_account_secret / forget_account_secret
 *    (src-tauri/src/account_secrets.rs): for each of the four SECRETS,
 *    whether the matching environment variable is already set on this PC
 *    (never its value), and, when it is not, whether Credential Manager
 *    holds one. One value into (or out of) Credential Manager. The box is
 *    emptied as soon as it is sent, and the value is never shown again -
 *    only whether one is saved, exactly like the web search keys' own boxes
 *    (web-search-settings.js). Never touches the backend or the phone.
 *  - get_account_addresses / save_account_address
 *    (src-tauri/src/account_addresses.rs): the eight ADDRESSES and the one
 *    choice, read from and written to the PC's own route
 *    (accounts.json beside web-search.json). An address is not a secret, so
 *    it is a plain settings file and the box shows what is saved - and the
 *    row says when an environment variable wins instead. A save is greyed
 *    while the event stream is stale, like every other change sent to the PC.
 *
 * There is no such page on the phone: deep config editing stays off it
 * (CLAUDE.md), and sending a secret over the link would send it somewhere
 * other than the one place it belongs.
 *
 * @module account-secrets-settings
 */

import { announce, currentLink, linkWords, onLink } from "./jarvis-link.js";
import {
  ADDRESSES_LOADING,
  ADDRESSES_MISSING,
  ADDRESSES_NOTE,
  ADDRESSES_TITLE,
  ADDRESS_HELP,
  ADDRESS_LABEL,
  ADDRESS_PLACEHOLDER,
  ADDRESS_SAVE_LABEL,
  addressStatusLine,
  FORGET_LABEL,
  HELP,
  LABEL,
  MASKED,
  MISSING,
  PLACEHOLDER,
  readAccountAddresses,
  readAccountSecrets,
  SAVE_LABEL,
  statusLine,
} from "./account-secrets.js";

const TAURI = globalThis.__TAURI__;
const IS_TAURI = Boolean(TAURI && TAURI.core && TAURI.core.invoke);
const $ = (id) => document.getElementById(id);

async function invoke(command, args = {}) {
  if (!IS_TAURI) throw new Error("no desktop backend");
  return TAURI.core.invoke(command, args);
}

const as = {
  section: $("account-secrets"),
  body: $("as-body"),
  status: $("as-status"),
  addressesTitle: $("as-addresses-title"),
  addressesNote: $("as-addresses-note"),
  addresses: $("as-addresses"),
  addressesState: $("as-addresses-state"),
};

const STALE = "Waiting for the link to catch up. Nothing can be sent until it does.";

let busy = false;

function node(tag, className, text) {
  const n = document.createElement(tag);
  if (className) n.className = className;
  if (text !== undefined) n.textContent = text;
  return n;
}

function say(text, tone, target) {
  const el = target || as.status;
  if (!el) return;
  el.textContent = text;
  if (tone) el.dataset.tone = tone;
  else delete el.dataset.tone;
}

/** An error in words, never a bridge error or JSON. */
function problemWords(error) {
  const said = String((error && error.message) || error || "").trim();
  if (!said || /[{}<>]|::|not allowed|undefined|null/i.test(said) || said.length > 400) {
    return "Try again in a moment, or restart Jarvis Desktop.";
  }
  return said;
}

function setBusy(v) {
  busy = v;
  if (!as.body) return;
  for (const el of as.section.querySelectorAll("button")) el.disabled = v;
  for (const el of as.section.querySelectorAll("input, select")) {
    if (!el.dataset.envSet) el.disabled = v;
  }
}

/** A save goes over the link to the PC, so it is greyed while the event
 *  stream is stale - the same rule web-search-settings.js follows. A box an
 *  environment variable already wins is disabled for its own reason and
 *  stays that way either way. */
function syncButtons() {
  if (!as.section) return;
  const live = linkWords(currentLink()).canAct;
  for (const el of as.section.querySelectorAll("[data-live]")) {
    if (el.dataset.envSet) continue;
    el.disabled = busy || !live;
    el.title = live ? "" : STALE;
  }
}

function row(entry) {
  const box = node("div", "sc-switch");
  box.dataset.secret = entry.name;
  const id = `as-${entry.name}`;
  const label = node("label", "label", LABEL[entry.name]);
  label.htmlFor = id;
  const line = node("div", "row sc-command");
  const input = document.createElement("input");
  input.type = MASKED[entry.name] ? "password" : "text";
  input.id = id;
  input.autocomplete = "off";
  input.spellcheck = false;
  input.placeholder = PLACEHOLDER[entry.name];
  input.disabled = entry.envSet;
  const save = node("button", "btn small", SAVE_LABEL);
  save.type = "button";
  save.disabled = entry.envSet;
  save.addEventListener("click", () => save_(entry, input));
  const forget = node("button", "btn ghost small", FORGET_LABEL);
  forget.type = "button";
  forget.hidden = entry.saved !== true;
  forget.disabled = entry.envSet;
  forget.addEventListener("click", () => forget_(entry));
  line.append(input, save, forget);
  box.append(label, line);
  box.append(node("p", "sc-line", statusLine(entry)));
  box.append(node("p", "note", HELP[entry.name]));
  return box;
}

/** One address (or the one choice) - the same look as a secret's own row,
 *  but the box SHOWS what is saved, because an address is not a secret. */
function addressRow(entry) {
  const box = node("div", "sc-switch");
  box.dataset.address = entry.name;
  const id = `as-${entry.name}`;
  const label = node("label", "label", ADDRESS_LABEL[entry.name]);
  label.htmlFor = id;
  const line = node("div", "row sc-command");
  let input;
  if (entry.choices) {
    input = document.createElement("select");
    input.id = id;
    for (const c of entry.choices) {
      const option = document.createElement("option");
      option.value = c.value;
      option.textContent = c.label;
      input.append(option);
    }
    input.value = entry.value;
  } else {
    input = document.createElement("input");
    input.type = "text";
    input.id = id;
    input.autocomplete = "off";
    input.spellcheck = false;
    input.placeholder = ADDRESS_PLACEHOLDER[entry.name];
    input.value = entry.value;
  }
  input.dataset.live = "true";
  if (entry.envSet) input.dataset.envSet = "1";
  input.disabled = entry.envSet;
  const save = node("button", "btn small", ADDRESS_SAVE_LABEL);
  save.type = "button";
  save.dataset.live = "true";
  if (entry.envSet) save.dataset.envSet = "1";
  save.disabled = entry.envSet;
  save.addEventListener("click", () => saveAddress(entry, input));
  line.append(input, save);
  box.append(label, line);
  box.append(node("p", "sc-line", addressStatusLine(entry)));
  box.append(node("p", "note", ADDRESS_HELP[entry.name]));
  return box;
}

function paint(entries) {
  if (!as.body) return;
  as.body.replaceChildren(...entries.map(row));
}

function paintAddresses(entries) {
  if (!as.addresses) return;
  as.addresses.replaceChildren(...entries.map(addressRow));
  syncButtons();
}

async function load() {
  if (!as.section || !IS_TAURI) return;
  try {
    const entries = readAccountSecrets(await invoke("get_account_secrets"));
    paint(entries);
  } catch (error) {
    say(problemWords(error) || MISSING, "bad");
  }
  await loadAddresses();
}

async function loadAddresses() {
  if (!as.addresses) return;
  say(ADDRESSES_LOADING, null, as.addressesState);
  try {
    const answer = await invoke("get_account_addresses");
    if (answer && answer.available === false) {
      // A PC without the route yet: said once, plainly, and no boxes.
      as.addresses.replaceChildren();
      say(String(answer.why || ADDRESSES_MISSING), "bad", as.addressesState);
      return;
    }
    const entries = readAccountAddresses(answer);
    paintAddresses(entries);
    const why = String((answer && answer.why) || "");
    say(why, why ? "bad" : null, as.addressesState);
  } catch (error) {
    as.addresses.replaceChildren();
    say(problemWords(error) || ADDRESSES_MISSING, "bad", as.addressesState);
  }
}

async function saveAddress(entry, input) {
  if (busy) return;
  const value = input.value;
  setBusy(true);
  try {
    const out = await invoke("save_account_address", { name: entry.name, value });
    const said = String((out && (out.said || out.error)) || "Saved.");
    say(said, out && out.ok === false ? "bad" : "ok");
    announce(said);
  } catch (error) {
    say(problemWords(error), "bad");
  } finally {
    setBusy(false);
  }
  await loadAddresses();
}

async function save_(entry, input) {
  if (busy) return;
  const value = input.value;
  // Emptied at once: the value is not kept in the page a moment longer than
  // the one call that saves it.
  input.value = "";
  if (!value.trim()) {
    say(`Paste a ${LABEL[entry.name].toLowerCase()} first.`, "bad");
    return;
  }
  setBusy(true);
  try {
    const out = await invoke("save_account_secret", { name: entry.name, value });
    say(String((out && out.said) || "Saved."), "ok");
    announce(as.status.textContent);
  } catch (error) {
    say(problemWords(error), "bad");
  } finally {
    setBusy(false);
  }
  await load();
}

async function forget_(entry) {
  if (busy) return;
  setBusy(true);
  try {
    const out = await invoke("forget_account_secret", { name: entry.name });
    say(String((out && out.said) || "Removed."), "ok");
  } catch (error) {
    say(problemWords(error), "bad");
  } finally {
    setBusy(false);
  }
  await load();
}

if (as.section) {
  if (as.addressesTitle) as.addressesTitle.textContent = ADDRESSES_TITLE;
  if (as.addressesNote) as.addressesNote.textContent = ADDRESSES_NOTE;
  load();
  onLink(() => syncButtons());
  document.addEventListener("visibilitychange", () => {
    if (!document.hidden) load();
  });
}
