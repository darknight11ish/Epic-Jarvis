/**
 * Settings -> "Thinking levels": per running model (Section 5.5).
 *
 * Commands:
 *  - get_thinking: lists running models and their supported levels;
 *  - set_thinking {role, level}: changes level at once, with NO approval card.
 *
 * @module thinking-settings
 */

import { announce, currentLink, linkWords, onLink } from "./jarvis-link.js";
import { LEVEL_LABELS, LEVELS, readThinking, WHY } from "./thinking-module.js";

const TAURI = globalThis.__TAURI__;
const IS_TAURI = Boolean(TAURI && TAURI.core && TAURI.core.invoke);
const $ = (id) => document.getElementById(id);

async function invoke(command, args = {}) {
  if (!IS_TAURI) throw new Error("no desktop backend");
  return TAURI.core.invoke(command, args);
}

const th = {
  section: $("thinking"),
  state: $("th-state"),
  body: $("th-body"),
  detail: $("th-detail"),
  notice: $("th-notice"),
  models: $("th-models"),
  status: $("th-status"),
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

function problemWords(error) {
  const said = String((error && error.message) || error || "").trim();
  if (!said || /[{}<>]|::|not allowed|undefined|null/i.test(said) || said.length > 400) {
    return "Try again in a moment, or restart Jarvis Desktop.";
  }
  return said;
}

function syncButtons() {
  if (!th.section) return;
  const live = linkWords(currentLink()).canAct;
  for (const el of th.section.querySelectorAll("[data-live]")) {
    el.disabled = busy || !live;
    el.title = live ? "" : STALE;
  }
}

function paint() {
  if (!th.section || !view) return;
  if (!view.available) {
    say(th.state, view.why);
    th.body.hidden = true;
    return;
  }
  th.state.textContent = "";
  th.body.hidden = false;
  say(th.detail, view.detail);
  say(th.notice, view.notice);
  th.models.replaceChildren();

  if (!view.models.length) {
    th.models.append(node("p", "note", "No models currently running."));
    return;
  }

  for (const m of view.models) {
    const card = node("div", "thinking-model-row card");
    card.style.marginBottom = "12px";
    card.style.padding = "10px";

    const head = node("div", "row");
    head.style.justifyContent = "space-between";
    head.style.alignItems = "baseline";

    const titleWrap = node("div");
    const nameSpan = node("strong", "thinking-model-name", m.name);
    nameSpan.style.marginRight = "8px";
    const refSpan = node("code", "quiet", m.model ? `(${m.model})` : "");
    titleWrap.append(nameSpan, refSpan);

    const curLvlSpan = node("span", "pill", LEVEL_LABELS[m.level] || m.level);
    curLvlSpan.dataset.tone = m.level === "off" ? "neutral" : "accent";
    head.append(titleWrap, curLvlSpan);
    card.append(head);

    const desc = node("p", "note", m.why || WHY[m.level] || "");
    desc.style.margin = "6px 0 10px 0";
    card.append(desc);

    const btnGroup = node("div", "row thinking-levels-group");
    btnGroup.style.gap = "6px";
    btnGroup.style.flexWrap = "wrap";

    for (const lvl of LEVELS) {
      const isSupp = m.supported.includes(lvl);
      const isCur = m.level === lvl;
      const b = node("button", `btn small ${isCur ? "primary" : "ghost"}`, LEVEL_LABELS[lvl] || lvl);
      b.dataset.live = "true";
      if (!isSupp) {
        b.disabled = true;
        b.title = `Not supported by ${m.model || "this model"}`;
        b.style.opacity = "0.4";
      } else {
        b.addEventListener("click", () => change(m.role, lvl));
      }
      btnGroup.append(b);
    }
    card.append(btnGroup);
    th.models.append(card);
  }

  syncButtons();
}

async function load() {
  if (!th.section || !IS_TAURI) return;
  try {
    view = readThinking(await invoke("get_thinking"));
  } catch (error) {
    view = { available: false, why: problemWords(error) };
  }
  paint();
}

async function change(role, level) {
  if (busy || !IS_TAURI) return;
  busy = true;
  say(th.status, "Changing…", "neutral");
  syncButtons();
  try {
    await invoke("set_thinking", { role, level });
    say(th.status, `Thinking set to ${level}.`, "good");
    announce(`Thinking level changed to ${level}.`);
    await load();
  } catch (error) {
    say(th.status, problemWords(error), "bad");
    paint();
  } finally {
    busy = false;
    syncButtons();
  }
}

if (th.section) {
  onLink((link) => {
    syncButtons();
    if (link.live && (!view || !view.available)) load();
  });
  load();
}
