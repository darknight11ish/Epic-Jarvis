/**
 * Settings -> Hardware and models: the graphics cards, what runs on them
 * now, and the three setups Jarvis offers for them (docs/HARDWARE-PROFILES.md,
 * backend/jarvis_hardware.py). Its real answers are
 * tests/fixtures/hardware-cases.json.
 *
 * NOTHING CHANGES UNTIL THE OWNER PICKS A SETUP, and picking one changes
 * nothing by itself either: it lists the steps. Each step is ONE button that
 * asks the PC for that step and nothing else, and the PC raises that step's
 * own approval card - the existing model-download and model-switch cards,
 * the second-card cards, or the new "make a model" card. Only the next step
 * has a button; the rest wait. There is no "do them all". The Rust command
 * (hardware.rs `hardware_step`) reads the step's route and body from the
 * PC's own answer, so this page never names a route.
 *
 * Every sentence about the cards and the setups is the PC's own
 * (`words`, `off`, `notes`, `summary`, `measured_words`); the few labels
 * here are shared word for word with the phone (net/Hardware.kt, checked by
 * backend/test_hardware.py).
 *
 * @module hardware-panel
 */

import { announce, APPROVE_WHERE, onQueue } from "./jarvis-link.js";

const TAURI = globalThis.__TAURI__;
const IS_TAURI = Boolean(TAURI && TAURI.core && TAURI.core.invoke);
const $ = (id) => document.getElementById(id);

async function invoke(command, args = {}) {
  if (!IS_TAURI) throw new Error("no desktop backend");
  return TAURI.core.invoke(command, args);
}

/** The labels this page adds. The phone's Hardware.kt has the same words. */
export const HW = {
  useThis: "Use this",
  recommended: "(recommended)",
  chosen: "Your choice",
  stop: "Stop using this setup",
  ask: "Ask",
  measure: "Measure",
  stepDone: "Done.",
  stepNext: "Next. It raises its own approval card.",
  stepLater: "Waits for the step before it.",
  stepCommand: "Run the one command below on your PC, then restart Ollama.",
  noLong: "Long conversations: no separate model.",
  noPictures: "Pictures: off.",
  restart: "Ollama has not picked these settings up yet. Quit Ollama (right-click its icon by the clock, then Quit Ollama) and start it again from the Start menu.",
  update: "This PC's Jarvis does not have the hardware part yet. Update the backend by running apply-patches.ps1, then open this again.",
};

/** The same words the second card uses while its card waits. */
const WAITING =
  `Waiting for your approval. Approve it ${APPROVE_WHERE} — nothing changes until you do.`;
const POLL_MS = 5000;
const POLL_FOR_MS = 10 * 60 * 1000;

const hw = {
  section: $("hardware"),
  state: $("hw-state"),
  body: $("hw-body"),
  found: $("hw-found"),
  cards: $("hw-cards"),
  now: $("hw-now"),
  nowBar: $("hw-now-bar"),
  presets: $("hw-presets"),
  steps: $("hw-steps"),
  stepsTitle: $("hw-steps-title"),
  stepList: $("hw-step-list"),
  stop: $("hw-stop"),
  commandBox: $("hw-command-box"),
  command: $("hw-command"),
  undo: $("hw-undo"),
  check: $("hw-check"),
  restart: $("hw-restart"),
  copyStatus: $("hw-copy-status"),
  measure: $("hw-measure"),
  measured: $("hw-measured"),
  details: $("hw-details-list"),
  later: $("hw-test-later"),
  status: $("hw-status"),
};

let last = null;
let seq = 0;
let busy = false;
let pollTimer = null;
let pollUntil = 0;

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

function sentence(text) {
  const s = String(text || "").trim().replace(/[.\s]+$/, "");
  return s ? `${s.charAt(0).toUpperCase()}${s.slice(1)}.` : "";
}

/** One card's memory bar: the 16 blocks and the sum, in words. */
function barLine(bar) {
  const p = node("p", "hw-bar");
  p.append(node("span", "hw-blocks", String(bar.blocks || "")));
  p.append(node("span", "hw-bar-words", ` ${bar.card}: ${bar.words}`));
  p.setAttribute("aria-label", `${bar.card}: ${bar.words}`);
  if (Number(bar.used_gib) > Number(bar.total_gib)) p.dataset.tone = "bad";
  return p;
}

function cardItem(card) {
  const li = node("li", "sc-gpu");
  li.dataset.role = card.used ? (card.chat_first ? "primary" : "second") : "unused";
  li.append(node("span", "sc-gpu-name", String(card.words || card.name || "A graphics card")));
  const bits = [];
  if (Array.isArray(card.sources) && card.sources.length) bits.push(`Found by ${card.sources.join(", ")}.`);
  if (card.desktop_share_gb !== null && card.desktop_share_gb !== undefined) {
    bits.push(`The desktop uses about ${Number(card.desktop_share_gb).toFixed(1)} GB of it (${card.desktop_share_how}).`);
  }
  if (card.best_effort) bits.push(`Best effort, not tested: ${card.best_effort}.`);
  if (bits.length) li.append(node("span", "sc-gpu-role", bits.join(" ")));
  return li;
}

function roleLine(label, role) {
  if (!role) return null;
  if (role.same_as_chat) return `${label}: ${role.words}.`;
  const how = { beside: " It stays loaded beside chat.", swap: " It takes turns with chat: a picture unloads chat for a moment.", turns: " It takes turns with the other extra model on that card." }[role.mode] || "";
  return `${label}: ${role.words}. It ${role.context_words}.${how}`;
}

function presetCard(p, status) {
  const box = node("div", "hw-preset");
  box.dataset.id = p.id;
  const chosen = status.chosen === p.id;
  const head = node("h3", "hw-preset-name", p.name);
  if (p.recommended) head.append(node("span", "hw-rec", ` ${HW.recommended}`));
  if (chosen) head.append(node("span", "hw-chosen", ` — ${HW.chosen}`));
  box.append(head);
  box.append(node("p", "note", p.summary));
  if (p.recommended && p.recommended_why) box.append(node("p", "sc-line", p.recommended_why));
  const lines = [
    roleLine("Chat", p.chat),
    p.long ? roleLine("Long conversations", p.long) : HW.noLong,
    p.pictures ? roleLine("Pictures", p.pictures) : HW.noPictures,
  ].filter(Boolean);
  for (const l of lines) box.append(node("p", "sc-line", l));
  for (const bar of p.bars || []) if (Number(bar.models_gib) > 0) box.append(barLine(bar));
  box.append(node("p", "sc-line", `${sentence(p.measured_words)}`));
  for (const why of p.best_effort_why || []) {
    const w = node("p", "sc-line", `Best effort, not tested: ${why}.`);
    w.dataset.tone = "warn";
    box.append(w);
  }
  const why = [...(p.off || []), ...(p.notes || [])];
  if (why.length) {
    box.append(node("p", "hw-off-title", "What is off, and why:"));
    const ul = node("ul", "hw-off");
    for (const o of why) ul.append(node("li", "", o));
    box.append(ul);
  }
  const use = node("button", "btn", HW.useThis);
  use.type = "button";
  use.id = `hw-use-${p.id}`;
  use.disabled = busy || chosen || !p.chat;
  use.addEventListener("click", () => choose(p.id, p.name));
  box.append(use);
  return box;
}

function stepItem(step) {
  const li = node("li", "hw-step");
  li.dataset.state = step.state;
  li.dataset.id = step.id;
  li.append(node("p", "hw-step-title", step.title));
  const words = step.kind === "command" && step.state !== "done" ? HW.stepCommand
    : { done: HW.stepDone, waiting: WAITING, next: HW.stepNext, later: HW.stepLater }[step.state] || "";
  const state = node("p", "sc-line", words);
  if (step.state === "done") state.dataset.tone = "ok";
  li.append(state);
  if (step.detail && step.state !== "done") li.append(node("p", "note", step.detail));
  if (step.modelfile) {
    const d = node("details", "more");
    d.append(node("summary", "more-detail", "Exactly what is made"));
    d.append(node("pre", "hw-modelfile", step.modelfile));
    li.append(d);
  }
  if (step.state === "next" && step.route) {
    const b = node("button", "btn small", HW.ask);
    b.type = "button";
    b.id = `hw-ask-${step.id}`;
    b.disabled = busy;
    b.setAttribute("aria-label", `${HW.ask}: ${step.title}`);
    b.addEventListener("click", () => askStep(step));
    li.append(b);
  }
  return li;
}

function showProblem(words) {
  last = null;
  hw.body.hidden = true;
  hw.state.hidden = false;
  hw.state.dataset.tone = "bad";
  hw.state.textContent = words;
  stopPoll();
}

function paint(status) {
  last = status;
  hw.state.hidden = true;
  delete hw.state.dataset.tone;
  hw.body.hidden = false;

  hw.found.textContent = status.found || "";
  hw.cards.replaceChildren(...(status.cards || []).map(cardItem));

  const now = status.now || {};
  say(hw.now, `${now.label || "Custom (your own setup)"}. ${now.words || ""}`.trim(),
    now.on_card_percent !== null && now.on_card_percent !== undefined && now.on_card_percent < 100 ? "bad" : null);
  hw.nowBar.replaceChildren(...(now.bar ? [barLine(now.bar)] : []));

  hw.presets.replaceChildren(...(status.presets || []).map((p) => presetCard(p, status)));
  if (status.chosen_stale) {
    const w = node("p", "sc-line", status.chosen_stale);
    w.dataset.tone = "warn";
    hw.presets.prepend(w);
  }

  const applying = status.applying;
  hw.steps.hidden = !applying;
  if (applying) {
    hw.stepsTitle.textContent = `Steps for "${applying.name}"`;
    hw.stepList.replaceChildren(...applying.steps.map(stepItem));
    hw.stop.disabled = busy;
  }

  const cmd = status.command || {};
  hw.commandBox.hidden = !cmd.line;
  hw.command.value = cmd.line || "";
  hw.undo.value = cmd.undo || "";
  hw.check.value = cmd.check || "";
  const pending = applying ? applying.restart_pending : cmd.restart_pending;
  say(hw.restart, pending === true ? HW.restart : "", pending === true ? "warn" : null);

  const m = status.measure || {};
  const lastRow = m.last;
  const bits = [];
  if (m.state === "running") bits.push("Measuring…");
  else if (m.why) bits.push(m.why);
  if (lastRow && Array.isArray(lastRow.roles)) {
    for (const r of lastRow.roles) {
      const parts = [r.model];
      if (typeof r.tokens_per_s === "number") parts.push(`${r.tokens_per_s} tokens a second`);
      if (typeof r.on_card_percent === "number") parts.push(`${r.on_card_percent}% on the card`);
      if (r.note) parts.push(r.note);
      bits.push(parts.join(", ") + ".");
    }
  }
  say(hw.measured, bits.join(" ") || "Not measured yet: every number above is calculated.",
    lastRow && lastRow.ok === false && (lastRow.roles || []).some((r) => r.spilled) ? "bad" : null);
  hw.measure.disabled = busy || m.state === "running";

  const shown = (status.presets || []).find((p) => p.id === (status.chosen || status.recommended));
  hw.details.replaceChildren(...((shown && shown.details) || []).map((d) => node("li", "", d)));
  hw.later.replaceChildren(...(status.test_later || []).map((t) => node("li", "", `${t.model}: ${t.why}.`)));

  const waiting = applying && applying.steps.some((s) => s.state === "waiting");
  if (waiting || m.state === "running") startPoll();
  else if (!pollUntil || Date.now() > pollUntil) stopPoll();
}

export async function loadHardware() {
  if (!IS_TAURI || !hw.section) return;
  const mine = ++seq;
  let answer;
  try {
    answer = await invoke("get_hardware");
  } catch (error) {
    if (mine !== seq) return;
    showProblem(`Jarvis could not be asked about your graphics cards. ${problemWords(error)}`);
    return;
  }
  if (mine !== seq) return;
  if (answer && answer.available === false) {
    showProblem(typeof answer.why === "string" && answer.why ? answer.why : HW.update);
    return;
  }
  if (!answer || typeof answer !== "object" || !Array.isArray(answer.presets)) {
    showProblem(`Jarvis's answer about your graphics cards could not be read. ${HW.update}`);
    return;
  }
  paint(answer);
}

function startPoll() {
  if (!pollUntil) pollUntil = Date.now() + POLL_FOR_MS;
  clearTimeout(pollTimer);
  if (Date.now() > pollUntil) return;
  pollTimer = setTimeout(() => {
    pollTimer = null;
    if (!document.hidden) loadHardware();
  }, POLL_MS);
}

function stopPoll() {
  clearTimeout(pollTimer);
  pollTimer = null;
  pollUntil = 0;
}

async function run(work, busyWords) {
  if (busy) return;
  busy = true;
  say(hw.status, busyWords);
  if (last) paint(last);
  try {
    const out = await work();
    const words = out && out.pending === true ? WAITING
      : out && typeof out.message === "string" && out.message ? out.message
      : "Done.";
    say(hw.status, words, "ok");
    announce(words);
  } catch (error) {
    say(hw.status, problemWords(error), "bad");
    announce(hw.status.textContent, "assertive");
  } finally {
    busy = false;
  }
  pollUntil = 0;
  startPoll();
  await loadHardware();
}

function choose(id, name) {
  return run(() => invoke("apply_hardware", { preset: id }), `Choosing "${name}"…`);
}

function askStep(step) {
  return run(() => invoke("hardware_step", { stepId: step.id }), `Asking: ${step.title}…`);
}

function copyButton(buttonId, inputId) {
  const b = $(buttonId);
  const input = $(inputId);
  if (!b || !input) return;
  b.addEventListener("click", async () => {
    input.select();
    let copied = false;
    try {
      await navigator.clipboard.writeText(input.value);
      copied = true;
    } catch {
      try { copied = document.execCommand("copy"); } catch { copied = false; }
    }
    say(hw.copyStatus, copied ? "Copied. Paste it into PowerShell and press Enter." : "Select it and press Ctrl+C.",
      copied ? "ok" : null);
  });
}

export function startHardwarePanel() {
  if (!hw.section) return;
  copyButton("hw-command-copy", "hw-command");
  copyButton("hw-undo-copy", "hw-undo");
  copyButton("hw-check-copy", "hw-check");
  hw.stop.addEventListener("click", () =>
    run(() => invoke("apply_hardware", { preset: null }), "Stopping…"));
  hw.measure.addEventListener("click", () =>
    run(() => invoke("measure_hardware"), "Starting to measure…"));
  // A card being answered changes the queue; that is the moment a step is
  // done (or refused). There is no event for the step itself.
  onQueue(() => {
    if (last && last.applying) loadHardware();
  });
  document.addEventListener("visibilitychange", () => {
    if (!document.hidden) loadHardware();
  });
  loadHardware();
}

startHardwarePanel();
