/**
 * Settings -> "When a captcha stops Jarvis" (the owner's own decision of
 * 2026-10-09: "1 by default with the option for 2 in the settings of Jarvis";
 * backend/jarvis_handoff_front.py; docs/CAPTCHA-HANDOFF-DESIGN.md).
 *
 * One Rust command (src-tauri/src/handoff.rs `handoff_front`), Settings only:
 *  - read: the choice, its two names, the PC's own lines and whether a card is
 *    waiting. A read: never held on a stale link.
 *  - set:  "leave_in_place" is applied at once, from either app, and never held
 *    (it only makes Jarvis do less - it touches no window at all);
 *    "bring_to_front" raises ONE approval card on the PC, decided in the Jarvis
 *    bar with Windows Hello, and is held on a stale link (rule 4 only holds
 *    what loosens).
 *
 * The page shows what the PC says and nothing more. It never pictures a browser
 * window, never taps or types anything, never raises a window itself, and never
 * names one of the hand-off's own picture or input routes: the real window is on
 * this PC, which is exactly why "Leave it where it is" is safe (tests/handoff.mjs
 * and tests/handoff-front.mjs check the desktop never calls them).
 *
 * @module handoff-front
 */

import { currentLink, linkWords, onLink } from "./jarvis-link.js";
import {
  BRING_TO_FRONT,
  DEFAULT_FRONT,
  FRONT_HELP,
  FRONT_LABELS,
  FRONT_MODES,
  HANDOFF_FRONT,
  frontBody,
  frontView,
  isLoosening,
  words,
} from "./handoff-front-rules.js";

const TAURI = globalThis.__TAURI__;
const IS_TAURI = Boolean(TAURI && TAURI.core && TAURI.core.invoke);
const $ = (id) => document.getElementById(id);

const el = {
  body: $("hf-body"),
  title: $("hf-title"),
  detail: $("hf-detail"),
  choices: $("hf-choices"),
  line: $("hf-line"),
  hello: $("hf-hello"),
  waitingLink: $("hf-waiting-link"),
  why: $("hf-why"),
  say: $("hf-status"),
  state: $("hf-state"),
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
  return text || HANDOFF_FRONT.unread;
}

/** The two choices as radio buttons, built once. The words are textContent. */
function buildChoices() {
  if (!el.choices || el.choices.childElementCount) return;
  FRONT_MODES.forEach((id) => {
    const row = document.createElement("label");
    row.className = "toggle";
    const input = document.createElement("input");
    input.type = "radio";
    input.name = "handoff-front";
    input.value = id;
    input.id = `hf-${id}`;
    const span = document.createElement("span");
    span.id = `hf-${id}-label`;
    span.textContent = FRONT_LABELS[id];
    row.append(input, span);
    el.choices.append(row);
    const help = document.createElement("p");
    help.className = "note";
    help.id = `hf-${id}-help`;
    help.textContent = FRONT_HELP[id];
    el.choices.append(help);
  });
}

function paint() {
  if (!el.body) return;
  el.title.textContent = HANDOFF_FRONT.title;
  el.detail.textContent = HANDOFF_FRONT.detail;
  el.hello.textContent = HANDOFF_FRONT.opensWindowsHello;
  buildChoices();
  const mode = view ? view.mode : DEFAULT_FRONT;
  const waiting = Boolean(view && view.waiting);
  const looseningBlocked = !live() || waiting;
  FRONT_MODES.forEach((id) => {
    const input = $(`hf-${id}`);
    const label = $(`hf-${id}-label`);
    if (!input || !label) return;
    input.checked = id === mode;
    // "Leave it where it is" is never held: it only makes Jarvis do less
    // (rule 4).
    input.disabled = busy || (isLoosening(id) && looseningBlocked);
    label.textContent =
      id === mode ? `${FRONT_LABELS[id]} (in use)` : FRONT_LABELS[id];
  });
  // The reason is on the screen, not only in a tooltip.
  const held = !live() && !waiting && view && view.mode !== BRING_TO_FRONT;
  el.waitingLink.textContent = held ? HANDOFF_FRONT.waitingLink : "";
  el.waitingLink.hidden = !held;
  el.line.textContent = view ? view.line : HANDOFF_FRONT.unread;
  el.why.textContent = view && view.why ? view.why : "";
  el.why.hidden = !(view && view.why);
  if (el.state) el.state.hidden = Boolean(view);
}

async function load() {
  if (!el.body || !IS_TAURI) return;
  try {
    const raw = await TAURI.core.invoke("handoff_front", { action: "read" });
    view = frontView(raw);
  } catch (error) {
    // Either an older backend has no such setting, or this read failed while it
    // may well be "Bring it to the front": say so in words and do NOT show
    // "Leave it where it is" as if it were the choice (that would be a claim).
    view = null;
    el.body.hidden = false;
    el.line.textContent = refusedWords(error);
    if (el.state) el.state.hidden = true;
    el.waitingLink.hidden = true;
    el.why.hidden = true;
    buildChoices();
    FRONT_MODES.forEach((id) => {
      const input = $(`hf-${id}`);
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
  const body = frontBody(mode);
  if (!body) return;
  busy = true;
  say(HANDOFF_FRONT.asking);
  paint();
  try {
    const out = await TAURI.core.invoke("handoff_front", { action: "set", mode });
    say(words(out && out.message) || HANDOFF_FRONT.offNow, "ok");
  } catch (error) {
    say(refusedWords(error), "warn");
  } finally {
    busy = false;
  }
  await load();
}

if (el.body) {
  buildChoices();
  FRONT_MODES.forEach((id) => {
    const input = $(`hf-${id}`);
    if (input) input.addEventListener("change", () => choose(id));
  });
  onLink(() => paint());
  load();
}
