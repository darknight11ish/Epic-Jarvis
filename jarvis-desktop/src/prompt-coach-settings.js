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
 * FOUR MORE SETTINGS BESIDE THE SWITCH (the owner's answers, 2026-10-09).
 * The owner's verdict on the single switch was *"make sure it's effective and
 * has multiple settings, including an enable and disable"*, and they then
 * chose these four: when it speaks up, how blunt it is, what it coaches on,
 * and per-platform behaviour. **This file does not contain a single one of
 * their names or lines.** The PC sends them (`jarvis_prompt_coach.SETTINGS`
 * through `settings_rows()`), one row each with every choice and the words
 * that explain it, and this module draws exactly what it was sent - the same
 * discipline as the four button words above, and the reason a new choice
 * appears in both apps by changing one Python tuple. A PC that answers without
 * them (an older backend) simply shows the switch alone, which is what it had
 * before: no invented rows, no empty pickers.
 *
 * One setting moves at a time through the same route: `set_prompt_coach
 * {key, value}`, at once, no card either way, for the same reason the master
 * switch has none - none of the four opens a way out of the PC, takes an
 * action, or changes what the coach is allowed to READ.
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
  "leaves the PC and nothing is acted on. Beside this switch are four more: " +
  "when it speaks up, how blunt it is, what it coaches on, and whether your " +
  "phone behaves the same. It also coaches for the AI you are sending to - the " +
  "model on this PC, or a cloud service - using what Jarvis knows about that " +
  "one; when it does not know an AI it says so instead of guessing.";
export const HEADING = "Prompt coach";
export const BUTTON = "Coach this";
export const SEND_MINE = "Send mine";
export const SEND_SUGGESTION = "Send the suggestion";

/** This app's own line for a PC whose Jarvis has no such route yet - the same
 *  shape as asks-first.js's MISSING, and byte for byte Rust's
 *  `prompt_coach::PROMPT_COACH_MISSING`. */
export const MISSING =
  "Your PC's Jarvis cannot show the prompt coach yet - run apply-patches.ps1 on the PC.";

/** The card's own elements. A FUNCTION, not a `const` read at module load: this
 * module is imported by tests/prompt-coach.mjs in plain Node to exercise
 * `readGroup`/`readPromptCoach`, where there is no `document` at all and a
 * top-level `getElementById` would throw before a single check ran (which is
 * exactly what it did, once). In the window it resolves to the same nodes it
 * always did - and every use below is inside a function, never at load. */
function els() {
  return {
    section: $("prompt-coach"),
    state: $("coach-state"),
    body: $("coach-body"),
    enabled: $("coach-enabled"),
    label: $("coach-enabled-label"),
    detail: $("coach-enabled-detail"),
    enabledStatus: $("coach-enabled-status"),
    groups: $("coach-groups"),
    status: $("coach-status"),
  };
}

/** True only in a window. Node's import of this module for its pure readers
 *  gets false, so nothing below touches a document that is not there. */
const IN_WINDOW = typeof document !== "undefined" && typeof globalThis.document === "object";

let view = null;
let busy = false;
let inFlight = "";

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
 * One row of `settings` as the PC sent it: `{key, name, names, value, default,
 * choices: [{value, name, detail}]}`. Returns null for anything that is not a
 * row this page can draw - a group with no key, no current value, or a value
 * that is not one of its own choices. Half a row is worse than none: it would
 * draw a picker nothing is selected in.
 */
export function readGroup(raw) {
  const r = raw && typeof raw === "object" ? raw : {};
  const key = words(r.key).trim();
  const choices = [];
  for (const c of Array.isArray(r.choices) ? r.choices : []) {
    const value = words(c && c.value).trim();
    if (!value) continue;
    choices.push({
      value,
      name: words(c && c.name).trim() || value,
      detail: words(c && c.detail).trim(),
    });
  }
  const value = words(r.value).trim();
  if (!key || !choices.length || !choices.some((c) => c.value === value)) return null;
  return {
    key,
    name: words(r.name).trim() || key,
    value,
    choices,
  };
}

/** Every row the PC sent that this page can draw, in the PC's own order. */
export function readGroups(raw) {
  const out = [];
  for (const item of Array.isArray(raw) ? raw : []) {
    const group = readGroup(item);
    if (group) out.push(group);
  }
  return out;
}

/**
 * `get_prompt_coach`'s answer (and `set_prompt_coach`'s - the PC sends the
 * same words back), read: the PC's own words where it sent them, the
 * byte-identical copy above where it did not, and `available: false` with the
 * PC's `why` for a PC whose Jarvis has no such route yet.
 *
 * `groups` is empty for a PC that answers with no `settings` list at all -
 * an older backend. That is not a failure and not a guess: the switch is
 * drawn alone, exactly as it was before the four existed.
 */
export function readPromptCoach(answer) {
  const a = answer && typeof answer === "object" ? answer : {};
  if (a.available === false) {
    return { available: false, why: words(a.why) || MISSING, on: false, groups: [] };
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
    groups: readGroups(a.settings),
    // The AIs Jarvis has notes for, and the number of days after which its own
    // notes say they may be out of date - so the card can say what the coach
    // knows about, and how fresh that is.
    targets: Array.isArray(a.targets) ? a.targets.filter((t) => typeof t === "string") : [],
    staleDays: typeof a.stale_days === "number" ? a.stale_days : 0,
  };
}

/** The one control is greyed only while a change is in flight. Nothing here is
 *  held on a stale link, so the link's own state never greys it. */
function syncBusy() {
  const pc = els();
  if (pc.enabled) pc.enabled.disabled = busy;
  if (!pc.groups) return;
  for (const el of pc.groups.querySelectorAll("input")) {
    // Only the row being changed is greyed; the rest stay live, so a slow
    // answer on one never blocks another.
    el.disabled = busy && el.dataset.key === inFlight;
  }
}

function node(tag, className, text) {
  const n = document.createElement(tag);
  if (className) n.className = className;
  if (text !== undefined) n.textContent = text;
  return n;
}

/** The four settings, drawn from the PC's own rows. */
function paintGroups() {
  const pc = els();
  if (!pc.groups) return;
  pc.groups.replaceChildren();
  if (!view || !view.available || !view.groups.length) {
    pc.groups.hidden = true;
    return;
  }
  pc.groups.hidden = false;
  for (const group of view.groups) {
    const box = node("div", "coach-group");
    box.dataset.key = group.key;
    const title = node("h3", "subhead", group.name);
    const choices = node("div", "choices");
    choices.setAttribute("role", "group");
    choices.setAttribute("aria-label", group.name);
    for (const c of group.choices) {
      const row = node("label", "theme-row");
      row.dataset.choice = c.value;
      const radio = document.createElement("input");
      radio.type = "radio";
      radio.name = `coach-${group.key}`;
      radio.value = c.value;
      radio.checked = c.value === group.value;
      radio.dataset.key = group.key;
      radio.addEventListener("change", () => {
        // changeChoice, NOT change: `change` is the master switch and takes a
        // boolean, so calling it with (key, value) sent `enabled = "<the key>"`
        // - a body the PC answers 400 to, and a wrong one. Not hypothetical:
        // tests/prompt-coach.mjs caught exactly that (2026-10-09).
        if (radio.checked) changeChoice(group.key, c.value);
      });
      const text = node("span", "theme-text");
      text.append(node("span", "theme-name", c.name), node("span", "theme-blurb", c.detail));
      const tick = node("span", "theme-check", "✓");
      tick.setAttribute("aria-hidden", "true");
      row.append(radio, text, tick);
      choices.append(row);
    }
    box.append(title, choices);
    pc.groups.append(box);
  }
  syncBusy();
}

function paint() {
  const pc = els();
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
  paintGroups();
  syncBusy();
}

async function load() {
  const pc = els();
  if (!pc.section || !IS_TAURI) return;
  try {
    view = readPromptCoach(await TAURI.core.invoke("get_prompt_coach"));
  } catch (error) {
    say(pc.state, `Could not read it: ${problemWords(error)}`, "bad");
    return;
  }
  paint();
}

/** The PC's own name for a setting, for the line after a change - the row's
 *  own `name`, never a second copy of it here. */
function nameOf(key) {
  const group = view && view.groups.find((g) => g.key === key);
  return group ? group.name : key;
}

async function change(on) {
  const pc = els();
  if (busy || !pc.section) return;
  busy = true;
  inFlight = "";
  syncBusy();
  say(pc.status, "Sending…");
  try {
    // The switch's own call, unchanged in meaning: one field, one level in.
    const out = readPromptCoach(
      await TAURI.core.invoke("set_prompt_coach", { change: { enabled: on } }),
    );
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

/** ONE of the four settings. Same route, same rules: at once, no card. */
async function changeChoice(key, value) {
  const pc = els();
  if (busy || !pc.section) return;
  busy = true;
  inFlight = key;
  syncBusy();
  say(pc.status, "Sending…");
  try {
    // THE ARGUMENT IS ONE NESTED OBJECT, and that is deliberate. Tauri binds a
    // page's arguments onto a command's parameters POSITIONALLY, so three
    // loose `Option`s meant `{key, value}` reached a `(enabled, key, value)`
    // command as `enabled = <the key>` - which tests/prompt-coach.mjs caught
    // (2026-10-09), and which is why `set_prompt_coach` now takes ONE `change`
    // object (`CoachChange` in prompt_coach.rs). One object has no order to
    // get wrong.
    const out = readPromptCoach(
      await TAURI.core.invoke("set_prompt_coach", { change: { key, value } }),
    );
    const group = out.groups.find((g) => g.key === key);
    const picked = group && group.choices.find((c) => c.value === value);
    const said = picked ? `${nameOf(key)}: ${picked.name}.` : `${nameOf(key)} changed.`;
    say(pc.status, said, "ok");
    announce(said);
    view = out;
  } catch (error) {
    // Put the radio back where the PC says it is: a picker left showing a
    // choice the PC refused is a claim the PC never made.
    say(pc.status, problemWords(error), "bad");
    announce(pc.status.textContent, "assertive");
  } finally {
    busy = false;
    inFlight = "";
  }
  await load();
  syncBusy();
}

// The wiring, only where there is a page to wire. Imported by a Node test for
// its pure readers, this module must not reach for a document at all.
if (IN_WINDOW) {
  const pc = els();
  if (pc.enabled) {
    pc.enabled.addEventListener("change", () => change(pc.enabled.checked));
  }
  load();
  document.addEventListener("visibilitychange", () => {
    if (!document.hidden) load();
  });
}
