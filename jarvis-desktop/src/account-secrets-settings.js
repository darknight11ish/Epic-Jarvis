/**
 * Settings -> Accounts (ease-of-use audit row 15, "Security G3";
 * JARVIS-API.md section 44; backend jarvis_token_store.resolve_secret,
 * jarvis_email.py, jarvis_calendar.py, jarvis_home.py).
 *
 * Three Rust commands (src-tauri/src/account_secrets.rs), Settings only:
 *  - get_account_secrets: for each of the four, whether the matching
 *    environment variable is already set on this PC (never its value), and,
 *    when it is not, whether Credential Manager holds one. Never touches
 *    the backend or the phone - both checks are made on this PC alone;
 *  - save_account_secret / forget_account_secret: one value into (or out
 *    of) Credential Manager on this PC. The box is emptied as soon as it is
 *    sent, and the value is never shown again - only whether one is saved,
 *    exactly like the web search keys' own boxes (web-search-settings.js).
 *
 * There is no such page on the phone: deep config editing stays off it
 * (CLAUDE.md), and sending a value over the link would send it somewhere
 * other than the one place it belongs.
 *
 * @module account-secrets-settings
 */

import { announce } from "./jarvis-link.js";
import {
  FORGET_LABEL,
  HELP,
  LABEL,
  MASKED,
  MISSING,
  PLACEHOLDER,
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
};

let busy = false;

function node(tag, className, text) {
  const n = document.createElement(tag);
  if (className) n.className = className;
  if (text !== undefined) n.textContent = text;
  return n;
}

function say(text, tone) {
  if (!as.status) return;
  as.status.textContent = text;
  if (tone) as.status.dataset.tone = tone;
  else delete as.status.dataset.tone;
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
  for (const el of as.body.querySelectorAll("button")) el.disabled = v;
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

function paint(entries) {
  if (!as.body) return;
  as.body.replaceChildren(...entries.map(row));
}

async function load() {
  if (!as.section || !IS_TAURI) return;
  try {
    const entries = readAccountSecrets(await invoke("get_account_secrets"));
    paint(entries);
  } catch (error) {
    say(problemWords(error) || MISSING, "bad");
  }
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
  load();
  document.addEventListener("visibilitychange", () => {
    if (!document.hidden) load();
  });
}
