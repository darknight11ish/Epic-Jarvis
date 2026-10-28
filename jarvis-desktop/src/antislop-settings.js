/**
 * Settings -> "How Jarvis talks" -> "Anti-Slop filter" (2026-10-28;
 * JARVIS-API.md section 159; backend jarvis_antislop.py).
 *
 * Two Rust commands (src-tauri/src/antislop.rs), Settings only:
 *  - get_antislop: the whole state, in the PC's own shape;
 *  - set_antislop {change}: ONE change - the master switch, one scope, the
 *    During/After mode, the Delivery Gate, the Liveliness dials or the em-dash
 *    exemption.
 *
 * NEITHER IS HELD ON A STALE LINK, and neither raises an approval card, in
 * either direction. The anti-slop filter changes the wording and the output
 * quality of an answer; it opens no way out of the PC, reads no folder, takes
 * no action and loosens no rule - the same class as the prompt coach beside it
 * (prompt_coach.rs). So the link's own state never greys a control here, and
 * that is a decision rather than an omission: it is said on screen and in
 * surfaces.toml.
 *
 * The card is drawn from antislop.js's words and the PC's own state, and it
 * re-reads on the "settings" event, so a change made on the phone (or by
 * typing "turn on anti-slop" in chat) appears here without a reload.
 *
 * @module antislop-settings
 */

import { announce, onEvent } from "./jarvis-link.js";
import {
  DIALS,
  DIAL_KEYS,
  DIAL_STEPS,
  EM_DASH_DETAIL,
  EM_DASH_LABEL,
  GATE_DETAIL,
  GATE_LABEL,
  MODES,
  REALITY,
  dialsAfter,
  dialWords,
  modeSaid,
  readAntislop,
  saidFor,
  scopeOn,
} from "./antislop.js";

const TAURI = globalThis.__TAURI__;
const IS_TAURI = Boolean(TAURI && TAURI.core && TAURI.core.invoke);
const $ = (id) => document.getElementById(id);

async function invoke(command, args = {}) {
  if (!IS_TAURI) throw new Error("no desktop backend");
  return TAURI.core.invoke(command, args);
}

const el = {
  section: $("antislop"),
  title: $("asf-title"),
  state: $("asf-state"),
  body: $("asf-body"),
  detail: $("asf-detail"),
  reality: $("asf-reality"),
  offNote: $("asf-off-note"),
  enabled: $("asf-enabled"),
  enabledLabel: $("asf-enabled-label"),
  enabledDetail: $("asf-enabled-detail"),
  scopesBlock: $("asf-scopes-block"),
  scopes: $("asf-scopes"),
  emDash: $("asf-em-dash"),
  emDashLabel: $("asf-em-dash-label"),
  emDashDetail: $("asf-em-dash-detail"),
  modesBlock: $("asf-modes-block"),
  modes: $("asf-modes"),
  gateRow: $("asf-gate-row"),
  gate: $("asf-gate"),
  gateLabel: $("asf-gate-label"),
  gateDetail: $("asf-gate-detail"),
  dialsBlock: $("asf-dials-block"),
  dials: $("asf-dials"),
  status: $("asf-status"),
};

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

/**
 * Greys the controls while a change is in flight, and for nothing else.
 * Deliberately NOT `syncButtons()` from manner-settings.js: that trades on
 * `data-live`, which exists to hold a change on a stale link, and nothing here
 * is held on a link at all.
 */
function syncBusy() {
  if (!el.section) return;
  for (const input of el.section.querySelectorAll("input")) input.disabled = busy;
}

/** Hides the halves that only matter while the filter is ON. */
function paintLive() {
  const on = Boolean(view && view.available && view.enabled);
  for (const block of [el.scopesBlock, el.modesBlock, el.dialsBlock, el.gateRow]) {
    if (block) block.hidden = !on;
  }
  // The gate switch only means anything when the UI scope is filtered.
  if (el.gateRow && on) el.gateRow.hidden = !scopeOn(view, "ui");
  if (el.offNote) el.offNote.hidden = on;
}

function paint() {
  if (!el.section || !view) return;
  if (!view.available) {
    say(el.state, view.why, "bad");
    if (el.body) el.body.hidden = true;
    if (el.offNote) el.offNote.hidden = true;
    return;
  }
  say(el.state, "", null);
  if (el.body) el.body.hidden = false;
  if (el.title) el.title.textContent = view.title;
  say(el.detail, view.detail);
  // The page's own sentence, not the PC's: the filter's enforcement split is a
  // fact about THIS version of the feature (a fixed list checked in code, the
  // rest prompt-guided), and a backend that sent its own words for it would be
  // free to drift from what the audit really does. Gemini review Q1.
  say(el.reality, REALITY);
  say(el.offNote, view.offNote);
  if (el.enabled) el.enabled.checked = view.enabled;
  if (el.enabledLabel) el.enabledLabel.textContent = view.title;
  if (el.enabledDetail) {
    el.enabledDetail.textContent = view.enabled
      ? "Filtering now. Every control below applies from the next turn."
      : "Off. Nothing is added to a prompt and nothing is rewritten.";
  }

  if (el.scopes) {
    el.scopes.replaceChildren();
    for (const scope of view.scopes) {
      const row = node("label", "asf-scope");
      row.dataset.scope = scope.id;
      const box = document.createElement("input");
      box.type = "checkbox";
      box.id = `asf-scope-${scope.id}`;
      box.checked = scope.on;
      box.addEventListener("change", () => changeScope(scope.id, box.checked));
      const words = node("span", "asf-scope-text");
      words.append(node("span", "asf-scope-name", scope.label),
                   node("span", "asf-scope-why", scope.why));
      row.append(box, words);
      el.scopes.append(row);
    }
  }

  // The em-dash exemption sits inside the scopes block - a hole cut in that
  // list, not a fourth scope - so paintLive() hides it with the block. OFF
  // unless the PC says a real yes (readAntislop reads `=== true`).
  if (el.emDashLabel) el.emDashLabel.textContent = EM_DASH_LABEL;
  if (el.emDashDetail) el.emDashDetail.textContent = EM_DASH_DETAIL;
  if (el.emDash) el.emDash.checked = view.allowEmDashes;

  if (el.modes) {
    el.modes.replaceChildren();
    for (const mode of MODES) {
      const row = node("label", "theme-row");
      row.dataset.mode = mode.id;
      const radio = document.createElement("input");
      radio.type = "radio";
      radio.name = "asf-mode";
      radio.value = mode.id;
      radio.checked = mode.id === view.mode;
      radio.addEventListener("change", () => {
        if (radio.checked) changeMode(mode.id);
      });
      const words = node("span", "theme-text");
      words.append(node("span", "theme-name", mode.label), node("span", "theme-blurb", mode.why));
      const tick = node("span", "theme-check", "\u2713");
      tick.setAttribute("aria-hidden", "true");
      row.append(radio, words, tick);
      el.modes.append(row);
    }
  }

  if (el.gate) el.gate.checked = view.gate;
  if (el.gateLabel) el.gateLabel.textContent = GATE_LABEL;
  if (el.gateDetail) el.gateDetail.textContent = GATE_DETAIL;

  if (el.dials) {
    el.dials.replaceChildren();
    for (const key of DIAL_KEYS) {
      const dial = DIALS[key];
      const row = node("div", "asf-dial");
      row.dataset.dial = key;
      const head = node("div", "asf-dial-head");
      head.append(node("span", "asf-dial-label", dial.label),
                  node("span", "asf-dial-why", dial.why));
      const group = node("div", "mn-pills");
      group.setAttribute("role", "group");
      group.setAttribute("aria-label", dial.label);
      for (const step of DIAL_STEPS) {
        const btn = node("button", "mn-btn", String(step));
        btn.type = "button";
        btn.dataset.dialKey = key;
        btn.dataset.value = String(step);
        btn.setAttribute("aria-pressed", view.dials[key] === step ? "true" : "false");
        btn.title = dialWords(key, step);
        btn.setAttribute("aria-label", dialWords(key, step));
        if (view.dials[key] === step) btn.dataset.active = "true";
        btn.addEventListener("click", () => changeDial(key, step));
        group.append(btn);
      }
      row.append(head, group);
      el.dials.append(row);
    }
  }
  paintLive();
  syncBusy();
}

async function load() {
  if (!el.section || !IS_TAURI) return;
  try {
    const raw = await invoke("get_antislop");
    view = readAntislop(raw);
  } catch (error) {
    say(el.state, `Could not read it: ${problemWords(error)}`, "bad");
    return;
  }
  paint();
}

/**
 * ONE change. The Rust command builds the POST body from the fields that were
 * given, so the switch's own call still sends exactly `{"enabled": bool}`.
 */
async function send(change, said) {
  if (busy) return false;
  busy = true;
  say(el.status, "Sending\u2026");
  syncBusy();
  let ok = false;
  try {
    const out = await invoke("set_antislop", { change });
    const words = String((out && (out.said || out.error)) || said || "Done.");
    ok = !(out && out.ok === false);
    say(el.status, words, ok ? "ok" : "bad");
    announce(words);
  } catch (error) {
    say(el.status, problemWords(error), "bad");
    announce(el.status.textContent, "assertive");
  } finally {
    busy = false;
    syncBusy();
  }
  // A failed change re-reads too: the page must show what the PC really holds
  // rather than the optimistic state of the control that was just refused.
  await load();
  return ok;
}

async function changeEnabled(on) {
  const ok = await send({ enabled: on === true }, saidFor("enabled", on === true));
  if (!ok && el.enabled && view && view.available) el.enabled.checked = view.enabled;
}

async function changeScope(id, on) {
  const ok = await send({ scope: id, on: on === true }, saidFor(id, on === true));
  if (!ok) await load();
}

async function changeMode(mode) {
  await send({ mode }, modeSaid(mode));
}

async function changeGate(on) {
  // The contract carries `show_delivery_gate_on_ui_tasks`; it is a switch on
  // the same POST, and it is only drawn while the UI scope is filtered.
  const ok = await send({ gate: on === true }, saidFor("gate", on === true));
  if (!ok && el.gate && view && view.available) el.gate.checked = view.gate;
}

/**
 * The em-dash exemption. ONE field, in the PC's own spelling
 * (`allow_em_dashes`), so ticking it cannot reset a scope, the mode, a dial or
 * the gate. It is NOT the voiceprint rule: Write Like Me already wins on its
 * own (`R-37`), and the row's detail line says so.
 */
async function changeEmDash(on) {
  const ok = await send({ allow_em_dashes: on === true }, saidFor("em_dash", on === true));
  if (!ok && el.emDash && view && view.available) {
    el.emDash.checked = view.allowEmDashes;
  }
}

async function changeDial(key, value) {
  await send({ dials: dialsAfter(view, key, value) }, `${DIALS[key].label} set to ${value}.`);
}

if (el.enabled) el.enabled.addEventListener("change", () => changeEnabled(el.enabled.checked));
if (el.gate) el.gate.addEventListener("change", () => changeGate(el.gate.checked));
if (el.emDash) el.emDash.addEventListener("change", () => changeEmDash(el.emDash.checked));

// A change made anywhere else - the phone, or "turn on anti-slop" typed into
// chat - arrives on the bus as one "settings" frame. The event is a doorbell,
// so this re-reads rather than trusting the frame's payload.
onEvent((frame) => {
  if (frame && frame.kind === "settings") load();
});

document.addEventListener("visibilitychange", () => {
  if (!document.hidden) load();
});

load();
