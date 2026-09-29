/**
 * Settings -> "Headless browser (Obscura)" (the owner's decision of 2026-09-29;
 * backend/jarvis_browser_engine.py and jarvis_obscura.py; JARVIS-API section 97).
 *
 * One Rust command (src-tauri/src/browser_engine.rs `browser_engine`), Settings
 * only:
 *  - read: the setting in the PC's own words (on or off, which browser Jarvis
 *    uses by default, the install status, the one PowerShell line).
 *  - on:   ONE approval card on the PC, decided in the Jarvis bar; nothing
 *    changes before a person says yes. Held on a stale link.
 *  - off:  at once, and never held. It also stops the program.
 *  - mode: Automatic, Visible or Headless. At once, no card.
 *
 * The page never runs a browser, never sees a web page and never sends a
 * proxy or an address: there is no such field here, and none can be added.
 *
 * @module browser-engine
 */

import { currentLink, linkWords, onLink } from "./jarvis-link.js";
import { BROWSER, MODE_IDS, browserView, words } from "./browser-engine-rules.js";

const TAURI = globalThis.__TAURI__;
const IS_TAURI = Boolean(TAURI && TAURI.core && TAURI.core.invoke);
const $ = (id) => document.getElementById(id);

const el = {
  body: $("be-body"),
  title: $("be-title"),
  detail: $("be-detail"),
  sw: $("be-switch"),
  swLabel: $("be-switch-label"),
  line: $("be-line"),
  status: $("be-state-line"),
  stealth: $("be-stealth"),
  modeTitle: $("be-mode-title"),
  mode: $("be-mode"),
  modeHelp: $("be-mode-help"),
  stepsTitle: $("be-steps-title"),
  lineText: $("be-line-text"),
  copy: $("be-copy"),
  stepsNote: $("be-steps-note"),
  say: $("be-status"),
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

function refusedWords(error) {
  const text = typeof error === "string" ? error : error && error.message ? String(error.message) : "";
  return text.trim() || BROWSER.unread;
}

function paint() {
  if (!el.body || !view) return;
  el.title.textContent = BROWSER.title;
  el.detail.textContent = BROWSER.detail;
  el.swLabel.textContent = BROWSER.switch;
  el.stealth.textContent = BROWSER.stealth;
  el.modeTitle.textContent = BROWSER.modeTitle;
  el.stepsTitle.textContent = BROWSER.stepsTitle;
  el.stepsNote.textContent = BROWSER.stepsNote;
  el.copy.textContent = BROWSER.copy;
  el.sw.indeterminate = false;
  el.sw.checked = view.checked;
  // Turning it ON needs a live link (a card is raised); turning it OFF never
  // waits (rule 4 only holds what loosens). While a card waits the switch stays
  // usable, so it can be turned back off (which takes the card back).
  el.sw.disabled = busy || (!view.checked && !live());
  el.sw.title = !view.checked && !live() ? linkWords(currentLink()).text : "";
  el.line.textContent = view.line;
  el.status.textContent = view.status;
  el.status.hidden = !view.status;
  // The mode list: text set with textContent (the words are fixed, never markup).
  if (el.mode.options.length !== MODE_IDS.length) {
    el.mode.replaceChildren(
      ...MODE_IDS.map((id) => Object.assign(document.createElement("option"), { value: id, textContent: BROWSER.modes[id] })),
    );
  }
  el.mode.value = view.mode;
  el.mode.disabled = busy;
  el.modeHelp.textContent = BROWSER.modeHelp[view.mode] || "";
  el.lineText.value = view.installLine;
  const has = Boolean(view.installLine);
  el.lineText.hidden = !has;
  el.copy.hidden = !has;
  el.stepsTitle.hidden = !has;
  el.stepsNote.hidden = !has;
}

async function load() {
  if (!el.body || !IS_TAURI) return;
  try {
    view = browserView(await TAURI.core.invoke("browser_engine", { action: "read" }));
  } catch (error) {
    // Either an older backend has no headless browser, or this read failed while
    // it may well be ON: say so in the PC's own words and do NOT show the switch
    // as off (that would be a claim). It is shown as "not known" (indeterminate)
    // and cannot be pressed until a read works.
    view = null;
    el.body.hidden = false;
    el.detail.textContent = "";
    el.line.textContent = refusedWords(error);
    el.status.hidden = true;
    el.sw.indeterminate = true;
    el.sw.disabled = true;
    el.mode.disabled = true;
    return;
  }
  el.body.hidden = false;
  paint();
  // While a card waits, look again now and then so the switch follows the answer.
  clearTimeout(poll);
  if (view.waiting) poll = setTimeout(load, 3000);
}

async function setSwitch(on) {
  if (busy) return;
  busy = true;
  say(on ? BROWSER.asking : BROWSER.turningOff);
  paint();
  try {
    const out = await TAURI.core.invoke("browser_engine", { action: on ? "on" : "off" });
    say(on ? BROWSER.askedCard : words(out && out.message) || BROWSER.off, "ok");
  } catch (error) {
    say(refusedWords(error), "warn");
  } finally {
    busy = false;
  }
  await load();
}

async function setMode(mode) {
  if (busy) return;
  busy = true;
  paint();
  try {
    await TAURI.core.invoke("browser_engine", { action: "mode", mode });
    say(BROWSER.modeSaved, "ok");
  } catch (error) {
    say(refusedWords(error), "warn");
  } finally {
    busy = false;
  }
  await load();
}

async function copyLine() {
  try {
    await navigator.clipboard.writeText(view ? view.installLine : "");
    say(BROWSER.copied, "ok");
  } catch {
    // No clipboard: select the line so Ctrl+C works.
    el.lineText.focus();
    el.lineText.select();
  }
}

if (el.body) {
  el.sw.addEventListener("change", (event) => setSwitch(event.target.checked));
  el.mode.addEventListener("change", (event) => setMode(event.target.value));
  el.copy.addEventListener("click", copyLine);
  el.lineText.addEventListener("focus", () => el.lineText.select());
  onLink(() => paint());
  load();
}
