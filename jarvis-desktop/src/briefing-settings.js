/**
 * Settings -> Morning briefing: when it arrives, and what it includes (the
 * owner's decisions of 2026-09-25; JARVIS-API.md section 22).
 *
 * Three Rust commands (src-tauri/src/brain/briefing.rs), Settings only:
 *  - get_briefing_setup: the briefing jobs and what a briefing includes (the
 *    briefing itself is taken out in Rust - it is read in the Brain);
 *  - set_briefing {every, at, days?}: ONE briefing that repeats. The PC
 *    raises the scheduler's own approval card (schedule_repeat) listing the
 *    next three times; nothing is set up before a yes. Held on a stale link,
 *    here (greyed) and in Rust;
 *  - stop_briefing {id}: ONE briefing, at once, no card. Held on a stale
 *    link. There is no "stop all".
 *  - set_briefing_senders {enabled}: "Show who new emails are from" (on by
 *    default). OFF is immediate and never held; ON raises ONE approval card
 *    on the PC (change_own_config) and is held on a stale link, here and in
 *    Rust - the same shape as the other settings that show more.
 *
 * The phone's Mind -> Morning briefing does the same (BriefingPlate.kt), in
 * the same words (briefing.js, net/Briefing.kt).
 *
 * @module briefing-settings
 */

import { announce, currentLink, linkWords, onEvent, onLink, onQueue } from "./jarvis-link.js";
import {
  ASKED,
  DAY_NAMES,
  EVERY,
  readBriefing,
  sendersView,
  SET_LABEL,
  SETUP_NONE,
  setupArgs,
  setupLine,
  sourceLines,
  SPOKEN,
  STOP_LABEL,
} from "./briefing.js";

const TAURI = globalThis.__TAURI__;
const IS_TAURI = Boolean(TAURI && TAURI.core && TAURI.core.invoke);
const $ = (id) => document.getElementById(id);

async function invoke(command, args = {}) {
  if (!IS_TAURI) throw new Error("no desktop backend");
  return TAURI.core.invoke(command, args);
}

const br = {
  section: $("briefing-settings"),
  state: $("br-state"),
  body: $("br-body"),
  setups: $("br-setups"),
  time: $("br-time"),
  every: $("br-every"),
  days: $("br-days"),
  set: $("br-set"),
  status: $("br-status"),
  reads: $("br-reads"),
  spoken: $("br-spoken"),
  senders: $("br-senders"),
  sendersRow: $("br-senders-row"),
  sendersLines: $("br-senders-lines"),
  sendersStatus: $("br-senders-status"),
};

const STALE = "Waiting for the link to catch up. Nothing can be sent until it does.";

let view = null;
let busy = false;
let every = "weekday";
const days = new Set([0, 1, 2, 3, 4]);

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
  if (!said || /[{}<>]|::|not allowed|undefined|null/i.test(said) || said.length > 300) {
    return "Try again in a moment, or restart Jarvis Desktop.";
  }
  return said;
}

function canAct() {
  return linkWords(currentLink()).canAct;
}

function syncButtons() {
  const live = canAct();
  for (const b of br.section ? br.section.querySelectorAll("button[data-live]") : []) {
    b.disabled = busy || !live;
    b.title = live ? "" : STALE;
  }
  paintSenders();
}

/** "Show who new emails are from": ON held on a stale link, OFF never. */
function paintSenders() {
  if (!br.senders || !view || !view.available) return;
  const v = sendersView(view.senders, canAct());
  if (br.sendersRow) br.sendersRow.hidden = !v.show;
  br.senders.checked = v.checked;
  br.senders.disabled = sendersBusy || !v.canChange;
  br.senders.title = v.canChange ? "" : STALE;
  if (br.sendersLines) br.sendersLines.replaceChildren(...v.lines.map((l) => node("p", "sc-line", l)));
}

let sendersBusy = false;

async function setSenders(on) {
  if (sendersBusy) return;
  if (on && !canAct()) {
    say(br.sendersStatus, STALE, "bad");
    paintSenders();
    return;
  }
  sendersBusy = true;
  paintSenders();
  say(br.sendersStatus, on ? "Asking…" : "Turning it off…");
  try {
    const out = await invoke("set_briefing_senders", { enabled: on });
    const words = String((out && (out.message || out.error)) || (on ? "Asked." : "Done."));
    say(br.sendersStatus, words, out && out.ok === false ? "bad" : "ok");
    announce(words);
  } catch (error) {
    say(br.sendersStatus, problemWords(error), "bad");
  } finally {
    sendersBusy = false;
  }
  await load();
}

function choiceButton(label, pressed, onClick) {
  const b = node("button", "choice", label);
  b.type = "button";
  b.setAttribute("aria-pressed", pressed ? "true" : "false");
  b.addEventListener("click", onClick);
  return b;
}

function paintForm() {
  if (!br.every) return;
  br.every.replaceChildren(...EVERY.map((e) => choiceButton(e.label, every === e.id, () => {
    every = e.id;
    paintForm();
  })));
  br.days.hidden = every !== "week";
  br.days.replaceChildren(...DAY_NAMES.map((name, i) => choiceButton(name, days.has(i), () => {
    if (days.has(i)) days.delete(i);
    else days.add(i);
    paintForm();
  })));
}

function paint() {
  if (!br.section) return;
  if (!view) return;
  if (!view.available) {
    say(br.state, view.why);
    br.body.hidden = true;
    return;
  }
  br.state.textContent = "";
  br.body.hidden = false;
  br.setups.replaceChildren();
  if (!view.setups.length) br.setups.append(node("li", "sc-gpu", SETUP_NONE));
  for (const job of view.setups) {
    const li = node("li", "sc-gpu");
    li.dataset.id = job.id;
    li.append(node("span", "sc-gpu-name", setupLine(job)));
    const stop = node("button", "btn ghost small", STOP_LABEL);
    stop.type = "button";
    stop.dataset.live = "true";
    stop.addEventListener("click", () => stopOne(job));
    li.append(stop);
    br.setups.append(li);
  }
  br.reads.replaceChildren(...sourceLines(view.sources).map((l) => node("li", "sc-gpu", l)));
  if (br.spoken) br.spoken.textContent = SPOKEN;
  if (br.set) {
    br.set.textContent = SET_LABEL;
    br.set.dataset.live = "true";
  }
  paintForm();
  syncButtons();
}

async function load() {
  if (!br.section || !IS_TAURI) return;
  try {
    view = readBriefing(await invoke("get_briefing_setup"));
  } catch (error) {
    say(br.state, `Could not read it: ${problemWords(error)}`, "bad");
    return;
  }
  paint();
}

async function setUp() {
  if (busy) return;
  const args = setupArgs(every, br.time ? br.time.value : "", [...days]);
  if (!args) {
    say(br.status, every === "week" ? "Pick at least one day and a time." : "Pick a time.", "bad");
    return;
  }
  busy = true;
  syncButtons();
  say(br.status, "Asking…");
  try {
    const out = await invoke("set_briefing", args);
    if (out && out.ok === false) {
      say(br.status, String(out.error || "Not set up."), "bad");
    } else {
      say(br.status, ASKED, "ok");
      announce(ASKED);
    }
  } catch (error) {
    say(br.status, problemWords(error), "bad");
    announce(br.status.textContent, "assertive");
  } finally {
    busy = false;
  }
  await load();
}

async function stopOne(job) {
  if (busy) return;
  busy = true;
  syncButtons();
  try {
    const out = await invoke("stop_briefing", { id: job.id });
    say(br.status, String((out && (out.said || out.error)) || "Stopped."), out && out.ok === false ? "bad" : "ok");
  } catch (error) {
    say(br.status, problemWords(error), "bad");
  } finally {
    busy = false;
  }
  await load();
}

if (br.set) br.set.addEventListener("click", setUp);
if (br.senders) br.senders.addEventListener("change", (e) => setSenders(e.target.checked));
onLink(() => syncButtons());
// A card answered (or expired): the setup may have changed. onQueue also
// delivers the current queue at once, which is the first read.
onQueue(() => load());
// A briefing job changed (`schedule` with kind "briefing", ids only).
onEvent((frame) => {
  if (frame && frame.kind === "schedule" && frame.data && frame.data.kind === "briefing") load();
});
document.addEventListener("visibilitychange", () => {
  if (!document.hidden) load();
});
paintForm();
