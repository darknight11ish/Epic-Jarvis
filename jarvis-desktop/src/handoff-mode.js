/**
 * Settings -> "When the phone does not answer" (the owner's own decision of
 * 2026-10-08: "make this a setting for both options with 1 as the default";
 * backend/jarvis_handoff_mode.py; docs/CAPTCHA-HANDOFF-DESIGN.md section 5).
 *
 * One Rust command (src-tauri/src/handoff.rs `handoff_mode`), Settings only:
 *  - read: the choice, its two names, the PC's own lines and whether a card is
 *    waiting. A read: never held on a stale link.
 *  - set:  "stop_early" is applied at once, from either app, and never held (it
 *    only makes Jarvis do less); "keep_offering" raises ONE approval card on the
 *    PC, decided in the Jarvis bar with Windows Hello, and is held on a stale
 *    link (rule 4 only holds what loosens).
 *
 * The page shows what the PC says and nothing more. It never pictures a browser
 * window, never taps or types anything, and never names one of the hand-off's
 * own picture or input routes: the real window is on this PC, which is exactly
 * why "Stop early" is safe (tests/handoff.mjs checks the desktop never calls
 * them).
 *
 * @module handoff-mode
 */

import { currentLink, linkWords, onLink } from "./jarvis-link.js";
import {
  DEFAULT_MODE,
  HANDOFF_MODE,
  MODE_HELP,
  MODE_LABELS,
  MODES,
  isLoosening,
  modeBody,
  modeView,
  words,
} from "./handoff-mode-rules.js";

const TAURI = globalThis.__TAURI__;
const IS_TAURI = Boolean(TAURI && TAURI.core && TAURI.core.invoke);
const $ = (id) => document.getElementById(id);

const el = {
  body: $("ho-body"),
  title: $("ho-title"),
  detail: $("ho-detail"),
  choices: $("ho-choices"),
  line: $("ho-line"),
  hello: $("ho-hello"),
  waitingLink: $("ho-waiting-link"),
  why: $("ho-why"),
  say: $("ho-status"),
  state: $("ho-state"),
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

// The reason in plain words: never a raw "HTTP 404" or a piece of JSON.
function refusedWords(error) {
  let text =
    typeof error === "string"
      ? error
      : error && error.message
        ? String(error.message)
        : "";
  text = text.trim();
  const start = text.indexOf("{");
  if (start >= 0) {
    try {
      const parsed = JSON.parse(text.slice(start));
      const said = parsed && (parsed.error || parsed.message);
      text = typeof said === "string" ? said.trim() : "";
    } catch {
      text = "";
    }
  }
  if (/^HTTP \d+/i.test(text)) text = "";
  return text || HANDOFF_MODE.unread;
}

/** The two choices as radio buttons, built once. The words are textContent. */
function buildChoices() {
  if (!el.choices || el.choices.childElementCount) return;
  MODES.forEach((id) => {
    const row = document.createElement("label");
    row.className = "toggle";
    const input = document.createElement("input");
    input.type = "radio";
    input.name = "handoff-mode";
    input.value = id;
    input.id = `ho-${id}`;
    const span = document.createElement("span");
    span.id = `ho-${id}-label`;
    span.textContent = MODE_LABELS[id];
    row.append(input, span);
    el.choices.append(row);
    const help = document.createElement("p");
    help.className = "note";
    help.id = `ho-${id}-help`;
    help.textContent = MODE_HELP[id];
    el.choices.append(help);
  });
}

function paint() {
  if (!el.body) return;
  el.title.textContent = HANDOFF_MODE.title;
  el.detail.textContent = HANDOFF_MODE.detail;
  el.hello.textContent = HANDOFF_MODE.opensWindowsHello;
  buildChoices();
  const mode = view ? view.mode : DEFAULT_MODE;
  const waiting = Boolean(view && view.waiting);
  const looseningBlocked = !live() || waiting;
  MODES.forEach((id) => {
    const input = $(`ho-${id}`);
    const label = $(`ho-${id}-label`);
    if (!input || !label) return;
    input.checked = id === mode;
    // "Stop early" is never held: it only makes Jarvis do less (rule 4).
    input.disabled = busy || (isLoosening(id) && looseningBlocked);
    label.textContent =
      id === mode ? `${MODE_LABELS[id]} (in use)` : MODE_LABELS[id];
  });
  // The reason is on the screen, not only in a tooltip.
  const held = !live() && !waiting && view && view.mode !== "keep_offering";
  el.waitingLink.textContent = held ? HANDOFF_MODE.waitingLink : "";
  el.waitingLink.hidden = !held;
  el.line.textContent = view ? view.line : HANDOFF_MODE.unread;
  el.why.textContent = view && view.why ? view.why : "";
  el.why.hidden = !(view && view.why);
  if (el.state) el.state.hidden = Boolean(view);
}

async function load() {
  if (!el.body || !IS_TAURI) return;
  try {
    const raw = await TAURI.core.invoke("handoff_mode", { action: "read" });
    view = modeView(raw);
  } catch (error) {
    // Either an older backend has no such setting, or this read failed while it
    // may well be "Keep offering it": say so in words and do NOT show "Stop
    // early" as if it were the choice (that would be a claim).
    view = null;
    el.body.hidden = false;
    el.line.textContent = refusedWords(error);
    if (el.state) el.state.hidden = true;
    el.waitingLink.hidden = true;
    el.why.hidden = true;
    buildChoices();
    MODES.forEach((id) => {
      const input = $(`ho-${id}`);
      if (input) {
        input.checked = false;
        input.disabled = true;
      }
    });
    return;
  }
  el.body.hidden = false;
  paint();
  // While a card waits, look again now and then so the screen follows the answer.
  clearTimeout(poll);
  if (view.waiting) poll = setTimeout(load, 3000);
}

async function choose(mode) {
  if (busy) return;
  const body = modeBody(mode);
  if (!body) return;
  busy = true;
  say(HANDOFF_MODE.asking);
  paint();
  try {
    const out = await TAURI.core.invoke("handoff_mode", { action: "set", mode });
    say(words(out && out.message) || HANDOFF_MODE.offNow, "ok");
  } catch (error) {
    say(refusedWords(error), "warn");
  } finally {
    busy = false;
  }
  await load();
}

if (el.body) {
  buildChoices();
  MODES.forEach((id) => {
    const input = $(`ho-${id}`);
    if (input) input.addEventListener("change", () => choose(id));
  });
  onLink(() => paint());
  load();
}
