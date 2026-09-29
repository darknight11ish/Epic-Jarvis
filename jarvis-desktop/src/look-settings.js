/**
 * Settings -> "Look at this and Watch with me" (the owner's decision of
 * 2026-09-28; docs/SCREEN-DESIGN.md; JARVIS-API sections 62 and 96; backend
 * jarvis_screen.py).
 *
 * One Rust command (src-tauri/src/look.rs `screen_never`), Settings only:
 *  - list: the Never look at list, in the PC's words. A read.
 *  - add {kind, value}: at once (it only makes Jarvis look at LESS).
 *  - remove {kind, value}: ONE approval card on the PC, decided in the Jarvis
 *    bar; nothing changes before a person says yes. Held on a stale link.
 * and `screen_status` for whether looking at the screen works on this PC.
 *
 * The keys ("Look at this", "Watch with me") are in Shortcuts; Watch with me
 * itself starts from the Jarvis bar's button, the tray and its own key. The
 * page never sees a picture or a word from the screen: there are none here.
 *
 * @module look-settings
 */

import { currentLink, linkWords, onLink } from "./jarvis-link.js";
import { neverView, PICTURE, pictureView, refusedWords, SETTINGS } from "./look-rules.js";

const TAURI = globalThis.__TAURI__;
const IS_TAURI = Boolean(TAURI && TAURI.core && TAURI.core.invoke);
const $ = (id) => document.getElementById(id);

const el = {
  section: $("screen-look"),
  title: $("sl-title"),
  detail: $("sl-detail"),
  state: $("sl-state"),
  body: $("sl-body"),
  neverTitle: $("sl-never-title"),
  neverDetail: $("sl-never-detail"),
  list: $("sl-list"),
  empty: $("sl-empty"),
  kind: $("sl-kind"),
  value: $("sl-value"),
  add: $("sl-add"),
  status: $("sl-status"),
  // Picture mode (a slow picture model on the processor; the owner's decision
  // of 2026-09-29).
  pBody: $("sp-body"),
  pTitle: $("sp-title"),
  pDetail: $("sp-detail"),
  pSwitch: $("sp-switch"),
  pSwitchLabel: $("sp-switch-label"),
  pLine: $("sp-line"),
  pMeasured: $("sp-measured"),
  pStepsTitle: $("sp-steps-title"),
  pLineText: $("sp-line-text"),
  pCopy: $("sp-copy"),
  pStepsNote: $("sp-steps-note"),
  pStatus: $("sp-status"),
};

let view = null;
let busy = false;
let poll = null;
let pView = null;
let pBusy = false;
let pPoll = null;

function node(tag, className, text) {
  const n = document.createElement(tag);
  if (className) n.className = className;
  if (text !== undefined) n.textContent = text;
  return n;
}

function live() {
  return linkWords(currentLink()).canAct;
}

function say(text, tone) {
  if (!el.status) return;
  el.status.textContent = text;
  if (tone) el.status.dataset.tone = tone;
  else delete el.status.dataset.tone;
}

function paint() {
  if (!el.section || !view) return;
  el.title.textContent = SETTINGS.title;
  el.detail.textContent = SETTINGS.detail;
  el.neverTitle.textContent = SETTINGS.neverTitle;
  el.neverDetail.textContent = SETTINGS.neverDetail;
  if (view.unreadable) {
    el.list.replaceChildren();
    el.empty.hidden = false;
    el.empty.textContent = SETTINGS.unreadable;
    el.add.disabled = true;
    return;
  }
  // textContent everywhere: the names are the owner's, never markup.
  el.list.replaceChildren(...view.rows.map((row) => {
    const li = node("li", "sc-gpu");
    li.append(node("span", "sc-gpu-name", row.name));
    li.append(node("span", "sc-gpu-role", `${row.kind} - ${row.tag}`));
    const rm = node("button", "btn small", SETTINGS.take);
    rm.type = "button";
    rm.disabled = busy || !live();
    rm.addEventListener("click", () => remove(row));
    li.append(rm);
    return li;
  }));
  const mine = view.rows.filter((r) => !r.builtIn).length;
  el.empty.hidden = mine > 0;
  el.empty.textContent = SETTINGS.empty;
  el.add.disabled = busy;
  if (view.pending) say(SETTINGS.pending);
  else if (view.lastWords && !el.status.textContent) say(view.lastWords);
}

async function load() {
  if (!el.section) return;
  if (!IS_TAURI) {
    el.state.textContent = "Open this in Jarvis Desktop to change the list.";
    return;
  }
  let status = null;
  try {
    status = await TAURI.core.invoke("screen_status");
  } catch (error) {
    el.state.textContent = refusedWords(error);
    el.state.hidden = false;
    el.body.hidden = true;
    return;
  }
  const s = (status && status.status) || {};
  if (s.available === false) {
    // Not on this PC yet: the PC says why, in its own words.
    el.state.textContent = String(s.unavailable_why || "Looking at the screen is not on this PC.");
    el.state.hidden = false;
  } else {
    el.state.hidden = true;
  }
  try {
    view = neverView(await TAURI.core.invoke("screen_never", { action: "list" }));
  } catch (error) {
    el.state.textContent = refusedWords(error);
    el.state.hidden = false;
    el.body.hidden = true;
    return;
  }
  el.body.hidden = false;
  paint();
  // While a card waits, look again now and then so the list follows the answer.
  clearTimeout(poll);
  if (view.pending) poll = setTimeout(load, 3000);
}

async function run(action, kind, value, working) {
  if (busy) return null;
  busy = true;
  say(working);
  paint();
  try {
    return await TAURI.core.invoke("screen_never", { action, kind, value });
  } catch (error) {
    say(refusedWords(error), "warn");
    return null;
  } finally {
    busy = false;
  }
}

async function add() {
  const value = (el.value.value || "").trim();
  if (!value) {
    say(el.kind.value === "site" ? SETTINGS.kindSite : SETTINGS.kindProgram, "warn");
    return;
  }
  const out = await run("add", el.kind.value, value, "Adding...");
  if (out) {
    say(out.added === false ? SETTINGS.already : SETTINGS.added, "ok");
    el.value.value = "";
  }
  await load();
}

async function remove(row) {
  const kind = row.kind === SETTINGS.site ? "site" : "program";
  const out = await run("remove", kind, row.name, "Asking for your yes...");
  if (out) say(SETTINGS.askedCard, "ok");
  await load();
}

// ── Picture mode ──────────────────────────────────────────────────────────

function pSay(text, tone) {
  if (!el.pStatus) return;
  el.pStatus.textContent = text;
  if (tone) el.pStatus.dataset.tone = tone;
  else delete el.pStatus.dataset.tone;
}

function pPaint() {
  if (!el.pBody || !pView) return;
  el.pTitle.textContent = PICTURE.title;
  el.pDetail.textContent = PICTURE.detail;
  el.pSwitchLabel.textContent = PICTURE.switch;
  el.pStepsTitle.textContent = PICTURE.stepsTitle;
  el.pStepsNote.textContent = PICTURE.stepsNote;
  el.pCopy.textContent = PICTURE.copy;
  el.pSwitch.checked = pView.checked;
  // Turning it ON needs a live link (a card is raised); turning it OFF never
  // waits (rule 4 only holds what loosens). While a card waits the switch stays
  // usable, so it can be turned back off (which takes the card back).
  el.pSwitch.disabled = pBusy || (!pView.checked && !live());
  el.pSwitch.title = !pView.checked && !live() ? linkWords(currentLink()).why || "" : "";
  el.pLine.textContent = pView.line;
  el.pMeasured.textContent = pView.measured;
  el.pMeasured.hidden = !pView.measured;
  el.pLineText.value = pView.installLine;
  const has = Boolean(pView.installLine);
  el.pLineText.hidden = !has;
  el.pCopy.hidden = !has;
  el.pStepsTitle.hidden = !has;
  el.pStepsNote.hidden = !has;
}

async function pLoad() {
  if (!el.pBody || !IS_TAURI) return;
  try {
    pView = pictureView(await TAURI.core.invoke("screen_picture", { action: "read" }));
  } catch (error) {
    // An older backend has no picture mode: say so in the PC's own words.
    el.pBody.hidden = false;
    el.pDetail.textContent = "";
    el.pLine.textContent = refusedWords(error);
    el.pSwitch.disabled = true;
    el.pSwitch.checked = false;
    return;
  }
  el.pBody.hidden = false;
  pPaint();
  // While a card waits, look again now and then so the switch follows the answer.
  clearTimeout(pPoll);
  if (pView.waiting) pPoll = setTimeout(pLoad, 3000);
}

async function pSet(on) {
  if (pBusy) return;
  pBusy = true;
  pSay(on ? PICTURE.asking : PICTURE.turningOff);
  pPaint();
  try {
    const out = await TAURI.core.invoke("screen_picture", { action: on ? "on" : "off" });
    pSay(on ? PICTURE.askedCard : words(out && out.message) || PICTURE.off, "ok");
  } catch (error) {
    pSay(refusedWords(error), "warn");
  } finally {
    pBusy = false;
  }
  await pLoad();
}

async function pCopy() {
  try {
    await navigator.clipboard.writeText(pView ? pView.installLine : "");
    pSay(PICTURE.copied, "ok");
  } catch {
    // No clipboard: select the line so Ctrl+C works.
    el.pLineText.focus();
    el.pLineText.select();
  }
}

function words(x) {
  return typeof x === "string" ? x.trim() : "";
}

if (el.pBody) {
  el.pSwitch.addEventListener("change", (event) => pSet(event.target.checked));
  el.pCopy.addEventListener("click", pCopy);
  el.pLineText.addEventListener("focus", () => el.pLineText.select());
  onLink(() => pPaint());
  pLoad();
}

if (el.section) {
  el.kind.replaceChildren(
    Object.assign(node("option", "", SETTINGS.kindProgram), { value: "program" }),
    Object.assign(node("option", "", SETTINGS.kindSite), { value: "site" }),
  );
  el.add.textContent = SETTINGS.add;
  el.add.addEventListener("click", add);
  el.value.addEventListener("keydown", (event) => {
    if (event.key === "Enter") add();
  });
  onLink(() => paint());
  load();
}
