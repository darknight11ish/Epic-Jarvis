/**
 * Settings -> Prompt coach (the owner's request of 2026-10-08 and their
 * answers the same day; docs/PROMPT-COACH-DESIGN.md; backend
 * jarvis_prompt_coach.py; JARVIS-API.md section 119).
 *
 * Two Rust commands (src-tauri/src/prompt_coach.rs), Settings only:
 *  - get_prompt_coach: whether the coach is on, in the PC's own words - a
 *    read;
 *  - set_prompt_coach {enabled}: the switch, OFF by default. At once, with NO
 *    approval card in EITHER direction, and neither direction is held on a
 *    stale link - unlike almost every other change sent to the PC. Nothing in
 *    this feature opens a way out of the PC, takes an action or loosens a
 *    rule: it reads words the chat is about to send to the same local model
 *    anyway, and it advises and acts on nothing (the design's choice B,
 *    written down so "no card" stays a decision and never an oversight). So
 *    there is nothing to grey here, no waiting line and no onLink.
 *
 * The words below are the PC's own - jarvis_prompt_coach.py's LABEL, DETAIL,
 * HEADING, BUTTON, SEND_MINE and SEND_SUGGESTION - kept byte for byte as the
 * fallback for a read that fails or a PC that answers without them, the same
 * copy asks-first.js keeps for the lights setting. They are exported for the
 * Jarvis bar's own piece of this work: the "Coach this" button beside the box,
 * and the panel that shows a critique, are a later piece, and they send and
 * read through their own commands. This file is only the switch.
 *
 * The command names are written out at each call rather than through a
 * wrapper like web-search-settings.js's own `invoke(command, args)`, so
 * tools/check_invoke_grants.py can read them at the call site without a new
 * entry in its own DYNAMIC_BELOW list.
 *
 * @module prompt-coach-settings
 */

import { announce } from "./jarvis-link.js";

const TAURI = globalThis.__TAURI__;
const IS_TAURI = Boolean(TAURI && TAURI.core && TAURI.core.invoke);
const $ = (id) => document.getElementById(id);

/* ── The PC's own words, byte for byte (jarvis_prompt_coach.py) ─────────── */

export const LABEL = "Prompt coach";
export const DETAIL =
  "Off (the default): nothing is read and there is no Coach this button. " +
  "On: a Coach this button appears beside the box where you type. Pressing it " +
  "asks the model on your own PC what is missing from your question - a score, " +
  "up to four gaps, and a rewritten version you can send instead of yours. It " +
  "never sends anything by itself, it never changes your words unless you pick " +
  "the rewritten one, and it is only ever advice: a low score does not stop you " +
  "sending what you wrote. The model on this PC is small, so its advice is " +
  "sometimes wrong and it misses things a bigger model would catch. Turning " +
  "this on or off happens at once - no approval card, because nothing here " +
  "leaves the PC and nothing is acted on.";
export const HEADING = "Prompt coach";
export const BUTTON = "Coach this";
export const SEND_MINE = "Send mine";
export const SEND_SUGGESTION = "Send the suggestion";

/** This app's own line for a PC whose Jarvis has no such route yet - the same
 *  shape as asks-first.js's MISSING, and byte for byte Rust's
 *  `prompt_coach::PROMPT_COACH_MISSING`. */
export const MISSING =
  "Your PC's Jarvis cannot show the prompt coach yet - run apply-patches.ps1 on the PC.";

const pc = {
  section: $("prompt-coach"),
  state: $("coach-state"),
  body: $("coach-body"),
  enabled: $("coach-enabled"),
  label: $("coach-enabled-label"),
  detail: $("coach-enabled-detail"),
  enabledStatus: $("coach-enabled-status"),
  status: $("coach-status"),
};

let view = null;
let busy = false;

function words(v) {
  return typeof v === "string" ? v : "";
}

function say(target, line, tone) {
  if (!target) return;
  target.textContent = line;
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

/**
 * `get_prompt_coach`'s answer (and `set_prompt_coach`'s - the PC sends the
 * same words back), read: the PC's own words where it sent them, the
 * byte-identical copy above where it did not, and `available: false` with the
 * PC's `why` for a PC whose Jarvis has no such route yet.
 */
export function readPromptCoach(answer) {
  const a = answer && typeof answer === "object" ? answer : {};
  if (a.available === false) {
    return { available: false, why: words(a.why) || MISSING, on: false };
  }
  return {
    available: true,
    on: a.on === true,
    why: words(a.why),
    label: words(a.label) || LABEL,
    detail: words(a.detail) || DETAIL,
    heading: words(a.heading) || HEADING,
    button: words(a.button) || BUTTON,
    sendMine: words(a.send_mine) || SEND_MINE,
    sendSuggestion: words(a.send_suggestion) || SEND_SUGGESTION,
  };
}

/** The one control is greyed only while a change is in flight. Nothing here is
 *  held on a stale link, so the link's own state never greys it. */
function syncBusy() {
  if (pc.enabled) pc.enabled.disabled = busy;
}

function paint() {
  if (!pc.section || !view) return;
  if (!view.available) {
    say(pc.state, view.why);
    pc.body.hidden = true;
    return;
  }
  pc.state.textContent = "";
  pc.body.hidden = false;
  pc.enabled.checked = view.on;
  pc.label.textContent = view.label;
  pc.detail.textContent = view.detail;
  // The PC's own sentence when its setting file could not be read - the coach
  // stays off then, and this is where it says so.
  say(pc.enabledStatus, view.why, view.why ? "bad" : null);
  syncBusy();
}

async function load() {
  if (!pc.section || !IS_TAURI) return;
  try {
    view = readPromptCoach(await TAURI.core.invoke("get_prompt_coach"));
  } catch (error) {
    say(pc.state, `Could not read it: ${problemWords(error)}`, "bad");
    return;
  }
  paint();
}

async function change(on) {
  if (busy || !pc.section) return;
  busy = true;
  syncBusy();
  say(pc.status, "Sending…");
  try {
    const out = readPromptCoach(await TAURI.core.invoke("set_prompt_coach", { enabled: on }));
    // The PC's own name for the switch, never a second copy of it.
    const said = out.on ? `${out.label} is on.` : `${out.label} is off.`;
    say(pc.status, said, "ok");
    announce(said);
  } catch (error) {
    // The PC did not take the change, so the box goes back to what the PC last
    // said rather than claiming a state it does not have. What went wrong is
    // said plainly, in the PC's own sentence where it sent one.
    if (view) pc.enabled.checked = view.on;
    say(pc.status, problemWords(error), "bad");
    announce(pc.status.textContent, "assertive");
  } finally {
    busy = false;
  }
  await load();
  syncBusy();
}

if (pc.enabled) {
  pc.enabled.addEventListener("change", () => change(pc.enabled.checked));
}

load();
document.addEventListener("visibilitychange", () => {
  if (!document.hidden) load();
});
