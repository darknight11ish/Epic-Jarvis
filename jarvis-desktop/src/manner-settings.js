/**
 * Settings -> "How Jarvis talks": warm and brief, or plain (the owner's
 * decision of 2026-09-25; JARVIS-API.md section 27).
 *
 * Two Rust commands (src-tauri/src/plain_errors.rs), Settings only:
 *  - get_manner: the choice, with the PC's own words for both;
 *  - set_manner {manner}: at once, NO approval card either way - it changes
 *    only how answers are worded. Held on a stale link, here (greyed) and
 *    in Rust, like every change sent to the PC.
 *
 * The phone's Mind -> "How Jarvis talks" does the same (MannerPlate.kt), in
 * the same words (manner.js, net/Manner.kt).
 *
 * @module manner-settings
 */

import { announce, currentLink, linkWords, onLink } from "./jarvis-link.js";
import { HUMOR_SAID, readManner, SAID } from "./manner.js";
import * as P from "./personalities.js";
import { mount as mountVoiceprint } from "./voiceprint-settings.js";

const TAURI = globalThis.__TAURI__;
const IS_TAURI = Boolean(TAURI && TAURI.core && TAURI.core.invoke);
const $ = (id) => document.getElementById(id);

async function invoke(command, args = {}) {
  if (!IS_TAURI) throw new Error("no desktop backend");
  return TAURI.core.invoke(command, args);
}

const mn = {
  section: $("manner"),
  state: $("mn-state"),
  body: $("mn-body"),
  detail: $("mn-detail"),
  choices: $("mn-choices"),
  list: $("mn-list"),
  spoken: $("mn-spoken"),
  status: $("mn-status"),
  humorTitle: $("mn-humor-title"),
  humor: $("mn-humor"),
  humorDetail: $("mn-humor-detail"),
  humorLabel: null,
  presetsBlock: $("mn-presets-block"),
  presetsNote: $("mn-presets-note"),
  hearNote: $("mn-hear-note"),
  presets: $("mn-presets"),
  dialsBlock: $("mn-tune-block"),
  dials: $("mn-dials"),
  sync: $("mn-sync"),
  syncDetail: $("mn-sync-detail"),
  mineBlock: $("mn-mine-block"),
  mine: $("mn-mine"),
  mineEmpty: $("mn-mine-empty"),
  customForm: $("mn-custom-form"),
  customName: $("mn-custom-name"),
  customLine: $("mn-custom-line"),
  customExample: $("mn-custom-example"),
  customBase: $("mn-custom-base"),
  customStatus: $("mn-custom-status"),
};

/** The personality half of the answer (personalities.js). */
let persona = null;

if (mn.humor && mn.humor.closest) mn.humorLabel = mn.humor.closest("label");

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

/** An error in words, never a bridge error or JSON. */
function problemWords(error) {
  const said = String((error && error.message) || error || "").trim();
  if (!said || /[{}<>]|::|not allowed|undefined|null/i.test(said) || said.length > 400) {
    return "Try again in a moment, or restart Jarvis Desktop.";
  }
  return said;
}

function syncButtons() {
  if (!mn.section) return;
  const live = linkWords(currentLink()).canAct;
  for (const el of mn.section.querySelectorAll("[data-live]")) {
    const held = el.dataset.needsPc === "no";
    el.disabled = busy || !live || held;
    el.title = held ? (el.dataset.pcWhy || "") : live ? "" : STALE;
  }
}

function paint() {
  if (!mn.section || !view) return;
  if (!view.available) {
    say(mn.state, view.why);
    mn.body.hidden = true;
    return;
  }
  mn.state.textContent = "";
  mn.body.hidden = false;
  say(mn.detail, view.detail);
  mn.choices.replaceChildren();
  for (const c of view.choices) {
    const row = node("label", "theme-row");
    row.dataset.choice = c.id;
    const radio = document.createElement("input");
    radio.type = "radio";
    radio.name = "mn-manner";
    radio.value = c.id;
    radio.checked = c.id === view.manner;
    radio.dataset.live = "true";
    radio.addEventListener("change", () => {
      if (radio.checked) change(c.id);
    });
    const text = node("span", "theme-text");
    text.append(node("span", "theme-name", c.label), node("span", "theme-blurb", c.why));
    const tick = node("span", "theme-check", "✓");
    tick.setAttribute("aria-hidden", "true");
    row.append(radio, text, tick);
    mn.choices.append(row);
  }
  say(mn.spoken, view.spoken);
  if (mn.humorTitle) mn.humorTitle.textContent = view.humorTitle;
  if (mn.humor) mn.humor.checked = view.humor;
  say(mn.humorDetail, view.humorDetail);
  paintPersona();
  syncButtons();
}

async function load() {
  if (!mn.section || !IS_TAURI) return;
  try {
    const raw = await invoke("get_manner");
    view = readManner(raw);
    persona = P.readPersonalities(raw);
  } catch (error) {
    say(mn.state, `Could not read it: ${problemWords(error)}`, "bad");
    return;
  }
  paint();
}

async function change(manner) {
  if (busy) return;
  busy = true;
  syncButtons();
  say(mn.status, "Sending…");
  try {
    const out = await invoke("set_manner", { manner });
    const said = String((out && (out.said || out.error)) || SAID[manner] || "Done.");
    say(mn.status, said, out && out.ok === false ? "bad" : "ok");
    announce(said);
  } catch (error) {
    say(mn.status, problemWords(error), "bad");
    announce(mn.status.textContent, "assertive");
  } finally {
    busy = false;
  }
  await load();
}

/** Humour (the owner's decision, 2026-09-27): on or off, it never asks
 * first either way - the same shape as `change()` above, its own Tauri
 * command. (Worded without that other word on purpose: tests/plain-errors.mjs
 * checks this file never mentions one.) */
async function changeHumor(on) {
  if (busy) return;
  busy = true;
  syncButtons();
  say(mn.status, "Sending…");
  try {
    const out = await invoke("set_humor", { on });
    const said = String((out && (out.said || out.error)) || HUMOR_SAID[on] || "Done.");
    say(mn.status, said, out && out.ok === false ? "bad" : "ok");
    announce(said);
  } catch (error) {
    say(mn.status, problemWords(error), "bad");
    announce(mn.status.textContent, "assertive");
    if (mn.humor && view) mn.humor.checked = view.humor; // revert an optimistic flip
  } finally {
    busy = false;
  }
  await load();
}

if (mn.humor) {
  mn.humor.addEventListener("change", () => changeHumor(mn.humor.checked));
}

onLink(() => syncButtons());
load();
document.addEventListener("visibilitychange", () => {
  if (!document.hidden) load();
});

// "Write like me" (jarvis_voiceprint.py; PR #665): the owner's own writing
// samples and their ON/OFF switch, in this same "How Jarvis talks" screen. The
// module is drawn by voiceprint-settings.js; this file only hands it the two
// real functions and the link's own staleness. A READ is never held, every
// write is held on a stale link here (isStale) and again on the PC, and
// neither direction asks the owner for a yes - they are local settings.
const voiceprint = mountVoiceprint(document.getElementById("voiceprint"), {
  invoke: (command, args) => invoke(command, args),
  confirm: (question) => window.confirm(question),
  isStale: () => !linkWords(currentLink()).canAct,
});
onLink(() => voiceprint?.syncLive());


/* ── Personality presets, the four dials, and "My personalities" ──────────
   2026-10-23 (Personality Presets, SLICE 2a). The eight built-in presets,
   their paired voice, the four tuning dials and the owner's own saved mixes.
   The words and the eight presets' data are personalities.js's; this half is
   only the page. The PC's own answer is preferred whenever it carries the
   fields; on a PC whose backend does not have them yet the new controls stay
   visible but disabled, with the plain "run apply-patches.ps1" sentence, and
   the two older choices above keep working exactly as they did. */

function personaButton(text, where) {
  const b = node("button", "mn-btn", text);
  b.type = "button";
  b.dataset.live = "true";
  b.dataset.pcTarget = where;
  return b;
}

function gated(el, pc) {
  if (!pc) {
    el.dataset.needsPc = "no";
    el.dataset.pcWhy = P.UPDATE_SENTENCE;
    el.title = P.UPDATE_SENTENCE;
  }
  return el;
}

function paintPersona() {
  if (!persona || !mn.presets) return;
  const pc = persona.pc;
  if (mn.list) mn.list.hidden = pc;
  if (mn.humorTitle) mn.humorTitle.hidden = pc;
  if (mn.humorLabel) mn.humorLabel.hidden = pc;
  for (const block of [mn.presetsBlock, mn.dialsBlock, mn.mineBlock]) {
    if (block) block.hidden = false;
  }
  if (mn.presetsNote) {
    mn.presetsNote.textContent = pc ? "" : P.UPDATE_SENTENCE;
    mn.presetsNote.hidden = pc;
  }
  // The honest note about what "Hear Sample" can play today: the base voice.
  // Shown even before the PC has the fields, because it describes the button,
  // not the PC.
  if (mn.hearNote) {
    mn.hearNote.textContent = P.HEAR_BASE_VOICE_NOTE;
    mn.hearNote.hidden = false;
  }
  const activeId = persona.active;

  mn.presets.replaceChildren();
  for (const preset of persona.presets) {
    const box = node("div", "mn-preset");
    box.dataset.preset = preset.id;
    const head = node("div", "mn-preset-head");
    head.append(node("span", "mn-badge", preset.badge),
                node("span", "mn-preset-title", preset.title));
    box.append(head, node("p", "mn-preset-desc", preset.description));
    if (preset.quote) box.append(node("p", "mn-preset-quote", `\u201c${preset.quote}\u201d`));
    box.append(node("p", "mn-voice", `Voice: ${P.voiceBadge(preset)}`));
    const actions = node("div", "mn-preset-actions");
    const hear = personaButton(P.HEAR_LABEL, preset.id);
    hear.classList.add("mn-hear");
    hear.dataset.hear = preset.id;
    hear.setAttribute("aria-label", `${P.HEAR_LABEL}: ${preset.title}`);
    hear.addEventListener("click", () => hearSample(preset, hear));
    const inUse = preset.id === activeId;
    const use = personaButton(inUse ? P.IN_USE : P.USE_LABEL, preset.id);
    use.classList.add("mn-use");
    use.dataset.use = preset.id;
    // One-shot action, not a toggle: no aria-pressed (the "In use" text and
    // data-active carry the state). The name says WHICH preset it acts on.
    use.setAttribute("aria-label",
      `${inUse ? P.IN_USE : P.USE_LABEL}: ${preset.title}`);
    if (inUse) use.dataset.active = "true";
    use.addEventListener("click", () => usePreset(preset));
    gated(hear, pc);
    gated(use, pc);
    actions.append(hear, use);
    box.append(actions);
    mn.presets.append(box);
  }

  mn.dials.replaceChildren();
  for (const key of P.DIAL_KEYS) {
    const dial = P.DIALS[key];
    const row = node("div", "mn-dial");
    row.dataset.dial = key;
    row.append(node("span", "mn-dial-label", dial.label));
    const group = node("div", "mn-pills");
    group.setAttribute("role", "group");
    group.setAttribute("aria-label", dial.label);
    for (const choice of dial.choices) {
      const on = persona.dials[key] === choice.id;
      const btn = personaButton(choice.label, key);
      btn.dataset.value = String(choice.id);
      btn.setAttribute("aria-pressed", on ? "true" : "false");
      if (on) btn.dataset.active = "true";
      btn.addEventListener("click", () => changeDials(key, choice.id));
      group.append(gated(btn, pc));
    }
    row.append(group);
    mn.dials.append(row);
  }

  if (mn.sync) {
    mn.sync.checked = persona.voiceSync;
    mn.sync.disabled = !pc;
    mn.sync.title = pc ? "" : P.UPDATE_SENTENCE;
    mn.sync.dataset.needsPc = pc ? "yes" : "no";
  }
  if (mn.syncDetail) mn.syncDetail.textContent = P.VOICE_SYNC_DETAIL;
  paintMine(pc);
}

function paintMine(pc) {
  if (!mn.mine) return;
  mn.mine.replaceChildren();
  const custom = persona.custom || [];
  if (mn.mineEmpty) {
    mn.mineEmpty.textContent = P.CUSTOM_EMPTY;
    mn.mineEmpty.hidden = custom.length > 0;
  }
  for (const person of custom) {
    const row = node("div", "mn-mine-row");
    row.dataset.custom = person.id;
    const text = node("div", "mn-mine-text");
    text.append(node("span", "mn-mine-name", person.title));
    if (person.description) text.append(node("span", "mn-mine-line", person.description));
    const actions = node("div", "mn-mine-actions");
    const use = personaButton(person.id === persona.active ? P.IN_USE : "Use", person.id);
    use.dataset.useCustom = person.id;
    use.setAttribute("aria-label",
      `${person.id === persona.active ? P.IN_USE : "Use"}: ${person.title}`);
    use.addEventListener("click", () => useCustom(person));
    const copy = personaButton("Duplicate", person.id);
    copy.setAttribute("aria-label", `Duplicate: ${person.title}`);
    copy.addEventListener("click", () => duplicateCustom(person));
    const drop = personaButton("Delete", person.id);
    drop.setAttribute("aria-label", `Delete: ${person.title}`);
    drop.addEventListener("click", () => deleteCustom(person));
    actions.append(gated(use, pc), gated(copy, pc), gated(drop, pc));
    row.append(text, actions);
    mn.mine.append(row);
  }
  if (mn.customForm) mn.customForm.hidden = !pc;
  if (mn.customBase) {
    const seen = mn.customBase.value;
    mn.customBase.replaceChildren();
    for (const preset of persona.presets) {
      const option = document.createElement("option");
      option.value = preset.id;
      option.textContent = preset.title;
      mn.customBase.append(option);
    }
    if (seen) mn.customBase.value = seen;
  }
}

async function sendPersona(body, said, where) {
  if (busy) return;
  busy = true;
  syncButtons();
  const note = where || mn.status;
  say(note, "Sending\u2026");
  let ok = false;
  try {
    const out = await invoke("set_manner", body);
    const words = String((out && (out.said || out.error)) || said || "Done.");
    ok = !(out && out.ok === false);
    say(note, words, ok ? "ok" : "bad");
    announce(words);
  } catch (error) {
    say(note, problemWords(error), "bad");
    announce(note.textContent, "assertive");
  } finally {
    busy = false;
    syncButtons();
  }
  if (ok) await load();
  return ok;
}

async function usePreset(preset) {
  await sendPersona(P.usePresetBody(preset), `${preset.title} is now in use.`);
}

async function useCustom(person) {
  await sendPersona({ personality: person.id }, `${person.title} is now in use.`);
}

async function changeDials(key, value) {
  const dials = { ...persona.dials, [key]: value };
  await sendPersona({ dials }, "The fine tuning is saved.");
}

async function changeSync(on) {
  const ok = await sendPersona({ voice_sync: on === true },
                               on ? "Jarvis's voice will follow the personality." :
                                    "Jarvis keeps its current voice.");
  if (!ok && mn.sync) mn.sync.checked = persona ? persona.voiceSync : false;
}

async function hearSample(preset, button) {
  if (busy) return;
  busy = true;
  syncButtons();
  const was = button.textContent;
  button.textContent = P.HEAR_BUSY;
  try {
    const out = await invoke("hear_voice_sample", P.sampleArgs(preset));
    const audio = String((out && out.audio) || "");
    if (!audio) throw new Error("The PC did not send a sample.");
    if (typeof Audio === "function") {
      try { new Audio(audio).play(); } catch (error) { /* no sound device here */ }
    }
    say(mn.status, `Playing ${P.voiceBadge(preset)}.`, "ok");
  } catch (error) {
    say(mn.status, problemWords(error), "bad");
  } finally {
    busy = false;
    button.textContent = was;
    syncButtons();
  }
}

async function duplicateCustom(person) {
  const base = persona.presets.find((p) => p.id === person.basedOn) || persona.presets[0];
  const copy = {
    id: P.customId(`${person.id}-copy`),
    name: `${person.title} (copy)`.slice(0, P.LIMITS.name),
    line: person.description,
    example: person.quote,
    dials: person.dials,
    basedOn: base ? base.id : P.DEFAULT_PRESET,
  };
  await sendPersona(P.saveCustomBody(copy), "The personality was copied.", mn.customStatus);
}

async function deleteCustom(person) {
  if (!window.confirm(P.DELETE_QUESTION)) return;
  await sendPersona(P.deleteCustomBody(person.id), "The personality was deleted.",
                    mn.customStatus);
}

async function saveCustom() {
  if (!mn.customForm || busy) return;
  const base = persona.presets.find((p) => p.id === (mn.customBase && mn.customBase.value)) ||
    persona.presets[0];
  const made = P.customPersonality({
    name: mn.customName ? mn.customName.value : "",
    line: mn.customLine ? mn.customLine.value : "",
    example: mn.customExample ? mn.customExample.value : "",
    dials: base ? base.dials : P.defaultDials(),
  }, base);
  if (made.why) {
    say(mn.customStatus, made.why, "bad");
    return;
  }
  const ok = await sendPersona(P.saveCustomBody(made), "The personality was saved.",
                               mn.customStatus);
  if (ok) {
    mn.customForm.reset();
    say(mn.customStatus, "Saved.", "ok");
  }
}

if (mn.sync) mn.sync.addEventListener("change", () => changeSync(mn.sync.checked));
if (mn.customForm) {
  mn.customForm.addEventListener("submit", (event) => {
    event.preventDefault();
    saveCustom();
  });
}
