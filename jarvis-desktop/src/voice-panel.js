/**
 * Settings -> Voice (training on this PC, how strict, private answers, the
 * guided test) and Settings -> Jarvis's voice (custom voices): the page.
 *
 * The words are in voice-training.js and custom-voices.js; this only draws
 * them and calls the Rust commands in voice_training.rs. Everything that
 * records opens this PC's microphone through the app, and the recordings
 * stay in the app's memory - this page is told a length and a loudness,
 * never given the audio, and names the recordings to send by slot.
 *
 * What changes anything goes one way only: making Jarvis stricter, going
 * back to the built-in voice, deleting a voice and turning the better voice
 * off happen at once; finishing a training, loosening a setting, adding a
 * voice, switching to one, turning the better voice on and using the
 * stricter bar the "someone else" check suggests only raise ONE approval
 * card, and the page says "waiting for your approval" until the PC says
 * how it ended. The guided test and the "someone else" check itself change
 * nothing. While the event stream is stale those are held
 * (by the Rust too, not only here). Nothing here approves anything.
 *
 * settings.js reads GET /api/voice/status and hands it to
 * `paintVoicePanel`; this module reads GET /api/voice/voices itself.
 *
 * @module voice-panel
 */

import { announce, APPROVE_WHERE, onEvent, onLink, onQueue } from "./jarvis-link.js";
import * as VT from "./voice-training.js";
import * as CV from "./custom-voices.js";

const TAURI = globalThis.__TAURI__;
const IS_TAURI = Boolean(TAURI && TAURI.core && TAURI.core.invoke);
const $ = (id) => document.getElementById(id);

async function invoke(command, args = {}) {
  if (!IS_TAURI) throw new Error("no desktop backend");
  return TAURI.core.invoke(command, args);
}

function node(tag, className, text) {
  const n = document.createElement(tag);
  if (className) n.className = className;
  if (text !== undefined) n.textContent = text;
  return n;
}

function button(text, onClick, { ghost = false, disabled = false, id } = {}) {
  const b = node("button", ghost ? "btn ghost" : "btn", text);
  b.type = "button";
  b.disabled = disabled;
  if (id) b.id = id;
  b.addEventListener("click", onClick);
  return b;
}

function line(text, tone, className = "sc-line") {
  const p = node("p", className, text);
  if (tone) p.dataset.tone = tone;
  return p;
}

function say(target, text, tone) {
  if (!target) return;
  target.textContent = text || "";
  if (tone) target.dataset.tone = tone;
  else delete target.dataset.tone;
}

/** An error in words; anything that is not a sentence is not shown as is. */
function problemWords(error) {
  const said = String((error && error.message) || error || "").trim();
  if (!said || /[{}<>]|::|not allowed|undefined|null/i.test(said) || said.length > 300) {
    return "Try again in a moment, or restart Jarvis Desktop.";
  }
  return said;
}

/** Said, when the event stream is stale, instead of sending a card. */
const HELD = "The connection to Jarvis is catching up, so this cannot be sent until it does.";
let linkStale = false;

/**
 * Which training outcome is THIS PC's, so "record the left-out ones again"
 * is offered only for a training made here. The PC's `last` does not say
 * which microphone it was about, so the page remembers when it sent one
 * (`sent`) and then the `at` of the first outcome that came after it
 * (`at`): that one outcome is ours, and no later one (a phone training,
 * say) is taken for it. A per-viewer convenience: without storage the offer
 * is simply not shown - never guessed.
 */
const TRAINED_KEY = "jarvis.voice.trainedAt";
function trainedMemo() {
  try {
    const m = JSON.parse(localStorage.getItem(TRAINED_KEY) || "null");
    return m && typeof m === "object" ? m : null;
  } catch {
    return null;
  }
}
function noteTrained() {
  try {
    localStorage.setItem(TRAINED_KEY, JSON.stringify({ sent: Date.now() / 1000, at: null }));
  } catch {
    /* see trainedMemo */
  }
}
/** Whether `last` is the outcome of this PC's own last training. */
function ownOutcome(last) {
  const memo = trainedMemo();
  const at = Number(last && last.at);
  if (!memo || !Number.isFinite(at)) return false;
  if (memo.at === null || memo.at === undefined) {
    // A few seconds of slack: the page's clock and the PC's are one PC's.
    if (at < Number(memo.sent) - 5) return false;
    try {
      localStorage.setItem(TRAINED_KEY, JSON.stringify({ sent: memo.sent, at }));
    } catch {
      return false;
    }
    return true;
  }
  return Number(memo.at) === at;
}

let status = null;
let reload = async () => {};

/* ==========================================================================
   The recorder: one Settings recording at a time, held by the app
   ========================================================================== */

const recorder = { slot: null, poll: null, auto: null, onLevel: null };

async function startRecording(slot, maxSeconds, onLevel, onAutoStop) {
  await invoke("start_voice_sample", { slot });
  recorder.slot = slot;
  recorder.onLevel = onLevel;
  recorder.poll = setInterval(async () => {
    try {
      const level = await invoke("voice_sample_level");
      if (recorder.onLevel) recorder.onLevel(Number(level) || 0);
    } catch {
      /* a level is a courtesy */
    }
  }, 120);
  recorder.auto = setTimeout(() => onAutoStop(), Math.max(1, maxSeconds) * 1000);
}

function clearRecorder() {
  clearInterval(recorder.poll);
  clearTimeout(recorder.auto);
  recorder.slot = null;
  recorder.onLevel = null;
}

async function stopRecording() {
  clearRecorder();
  return invoke("stop_voice_sample");
}

function cancelRecording() {
  if (!recorder.slot) return;
  clearRecorder();
  invoke("cancel_voice_sample").catch(() => {});
}

/* ==========================================================================
   The reader: sentences one at a time, Record / Stop / Redo, then a review
   ========================================================================== */

/**
 * Draws a list of sentences to read into `box`. `opts`: items [{slot,
 * text}], head (the round line), maxSeconds, sendLabel, sendNote, cardSend
 * (sending raises a card, so a stale link holds it), onSend(slots) ->
 * {ok, text, tone}, onCancel().
 */
function makeReader(box, opts) {
  const st = { index: 0, clips: new Map(), recording: false, problem: "", busy: false, reply: null };
  const total = opts.items.length;

  const recorded = () => opts.items.filter((it) => {
    const c = st.clips.get(it.slot);
    return c && !c.problem;
  });
  const seconds = () => recorded().reduce((s, it) => s + st.clips.get(it.slot).seconds, 0);

  async function record(item) {
    if (st.recording || st.busy) return;
    st.problem = "";
    st.busy = true;
    draw();
    try {
      await startRecording(item.slot, opts.maxSeconds, (level) => {
        const fill = box.querySelector(".vt-meter .progress-fill");
        if (fill) fill.style.width = `${Math.round(level * 100)}%`;
      }, () => stop(item));
      st.recording = true;
    } catch (error) {
      st.problem = problemWords(error);
    } finally {
      st.busy = false;
    }
    draw();
  }

  async function stop(item) {
    if (!st.recording) return;
    st.recording = false;
    st.busy = true;
    draw();
    try {
      const taken = await stopRecording();
      const problem = VT.clipProblem(taken, status);
      st.clips.set(item.slot, { seconds: Number(taken && taken.seconds) || 0, problem });
      st.problem = problem || "";
    } catch (error) {
      st.problem = problemWords(error);
    } finally {
      st.busy = false;
    }
    draw();
  }

  async function send() {
    if (st.busy) return;
    st.busy = true;
    st.reply = { text: "Sending…", tone: "" };
    draw();
    let out;
    try {
      out = await opts.onSend(opts.items.map((it) => it.slot));
    } catch (error) {
      out = { ok: false, text: problemWords(error), tone: "bad" };
    }
    st.busy = false;
    st.reply = out && !out.ok ? { text: out.text, tone: out.tone || "bad" } : null;
    if (out) announce(out.text, out.ok ? "polite" : "assertive");
    if (!out || !out.ok) draw();
  }

  function draw() {
    const nodes = [];
    if (opts.head) nodes.push(line(opts.head, "", "vt-head"));
    if (st.index < total) {
      const item = opts.items[st.index];
      const clip = st.clips.get(item.slot);
      nodes.push(line(`Sentence ${st.index + 1} of ${total}`, "", "vt-count"));
      nodes.push(line(item.text, "", "vt-sentence"));
      const row = node("div", "row");
      if (st.recording) {
        row.append(button("Stop", () => stop(item)));
      } else {
        row.append(button(clip ? "Redo this one" : "Record", () => record(item), { disabled: st.busy }));
      }
      let words = "";
      if (st.recording) words = "Recording. Read the sentence, then press Stop.";
      else if (st.problem) words = st.problem;
      else if (clip && !clip.problem) words = `Recorded: ${VT.lengthLabel(clip.seconds)}`;
      const note = node("span", "status", words);
      note.setAttribute("role", "status");
      if (st.problem) note.dataset.tone = "bad";
      else if (clip && !st.recording) note.dataset.tone = "ok";
      row.append(note);
      nodes.push(row);
      const meter = node("div", "progress-track vt-meter");
      meter.hidden = !st.recording;
      meter.append(node("div", "progress-fill"));
      nodes.push(meter);
      const moves = node("div", "row");
      if (st.index > 0) {
        moves.append(button("Back", () => { st.problem = ""; st.index -= 1; draw(); }, { ghost: true, disabled: st.recording }));
      }
      moves.append(button(st.index === total - 1 ? "Review" : "Next sentence", () => {
        st.problem = "";
        st.index += 1;
        draw();
      }, { disabled: st.recording || !clip || Boolean(clip.problem) }));
      moves.append(button("Cancel", () => { cancelRecording(); opts.onCancel(); }, { ghost: true }));
      nodes.push(moves);
    } else {
      nodes.push(line("Check your recordings", "", "vt-head"));
      const list = node("ul", "vt-review");
      opts.items.forEach((item, i) => {
        const c = st.clips.get(item.slot);
        const li = node("li");
        if (!c || c.problem) li.dataset.tone = "warn";
        const words = node("span", "vt-words");
        words.append(node("span", "", item.text), node("br"),
          node("span", "vt-len", c && !c.problem ? VT.lengthLabel(c.seconds) : c ? c.problem : "Not recorded"));
        li.append(words, button(c ? "Redo" : "Record", () => { st.index = i; st.reply = null; draw(); }, { ghost: true, disabled: st.busy }));
        list.append(li);
      });
      nodes.push(list);
      const blocker = VT.sendBlocker({
        recorded: recorded().length,
        total,
        linkBlocker: opts.cardSend && linkStale ? HELD : null,
        totalSeconds: seconds(),
        status,
      });
      const row = node("div", "row");
      row.append(button(opts.sendLabel, send, { disabled: Boolean(blocker) || st.busy }));
      row.append(button("Cancel", () => opts.onCancel(), { ghost: true, disabled: st.busy }));
      nodes.push(row);
      const said = st.reply || (blocker ? { text: blocker, tone: "warn" } : null);
      if (said) {
        const p = line(said.text, said.tone === "warn" ? "warn" : said.tone, "sc-line vt-reply");
        p.setAttribute("role", "status");
        nodes.push(p);
      }
      if (opts.sendNote) nodes.push(line(opts.sendNote, "", "note"));
    }
    box.replaceChildren(...nodes);
  }

  draw();
  return { draw };
}

/* ==========================================================================
   Training on this PC
   ========================================================================== */

const train = { view: "idle", plan: null, index: 0, message: "", reader: null, heldOnServer: false };

function trainBox() {
  return $("vt-train");
}

function slotsFor(round, items) {
  return items.map((i) => ({ slot: `t${round}-${i}`, text: VT.SENTENCES[i] }));
}

function startPlan(plan) {
  train.plan = plan;
  train.index = 0;
  train.message = "";
  train.view = plan.rounds.length ? "intro" : "idle";
  paintTrain();
}

async function finishOnly(round, add) {
  // Every round is already held on the PC: finish without clips.
  if (linkStale) {
    train.message = HELD;
    paintTrain();
    return;
  }
  try {
    const answer = await invoke("send_voice_training", { round, slots: [], add, finish: true, legacy: false });
    const reply = VT.roundReply(answer, APPROVE_WHERE);
    train.message = reply.text;
    if (reply.finished) {
      noteTrained();
      train.view = "sent";
    }
  } catch (error) {
    train.message = problemWords(error);
  }
  paintTrain();
  reload();
}

async function cancelTraining() {
  cancelRecording();
  train.view = "idle";
  train.plan = null;
  const hadServer = train.heldOnServer || Boolean(VT.heldSession(status));
  train.heldOnServer = false;
  invoke("discard_voice_samples", { prefix: "t" }).catch(() => {});
  if (hadServer) {
    try {
      const answer = await invoke("cancel_voice_training");
      train.message = VT.sentence(answer && (answer.message || answer.error)) || "Cancelled.";
    } catch (error) {
      train.message = problemWords(error);
    }
  } else {
    train.message = "Cancelled. Nothing was sent.";
  }
  paintTrain();
  reload();
}

function readRound() {
  const plan = train.plan;
  const r = plan.rounds[train.index];
  const last = train.index === plan.rounds.length - 1;
  train.view = "reading";
  const box = trainBox();
  train.reader = makeReader(box, {
    items: slotsFor(r.round, r.items),
    head: VT.roundLine(plan, train.index),
    maxSeconds: VT.limits(status).maxSeconds - 0.2,
    sendLabel: last ? "Send to your PC" : `Send round ${r.round}`,
    sendNote: last
      ? "Sending raises an approval card. Jarvis only learns your voice once you approve it."
      : "Your PC keeps this round in memory only; nothing changes until you finish and approve the card.",
    cardSend: last,
    onSend: async (slots) => {
      const answer = await invoke("send_voice_training", {
        round: r.round, slots, add: plan.add, finish: last && !plan.legacy, legacy: plan.legacy,
      });
      const reply = VT.roundReply(answer, APPROVE_WHERE);
      if (reply.held) {
        train.heldOnServer = true;
        train.index += 1;
        train.message = reply.text;
        train.view = "between";
        paintTrain();
        reload();
      } else if (reply.finished) {
        train.heldOnServer = false;
        noteTrained();
        train.message = reply.text;
        train.view = "sent";
        paintTrain();
        reload();
      }
      return { ok: reply.held || reply.finished, text: reply.text, tone: reply.tone };
    },
    onCancel: () => cancelTraining(),
  });
}

function paintTrain() {
  const box = trainBox();
  if (!box || !status) return;
  if (train.view === "reading") return; // the reader draws itself
  const nodes = [];
  const plan = train.plan;
  if (train.view === "intro") {
    for (const text of VT.introLines(plan, status)) nodes.push(line(text, "", "note"));
    nodes.push(line(VT.planLine(plan), "", "sc-line"));
    const row = node("div", "row");
    row.append(button("Start", () => readRound()), button("Cancel", () => cancelTraining(), { ghost: true }));
    nodes.push(row);
  } else if (train.view === "between") {
    const next = plan.rounds[train.index];
    nodes.push(line(train.message, "ok"));
    nodes.push(line(`When you are ready, round ${next.round}: ${next.ask}.`, "", "sc-line"));
    const row = node("div", "row");
    row.append(button(`Start round ${next.round}`, () => readRound()),
      button("Cancel the training", () => cancelTraining(), { ghost: true }));
    nodes.push(row);
  } else if (train.view === "sent") {
    nodes.push(line(train.message || VT.afterSending(APPROVE_WHERE), "ok"));
    nodes.push(line("Nothing changes until the card is approved. If nobody answers it, it expires and the recordings are deleted.", "", "note"));
    const row = node("div", "row");
    row.append(button("Done", () => { train.view = "idle"; train.message = ""; paintTrain(); }));
    nodes.push(row);
  } else {
    if (train.message) nodes.push(line(train.message, ""));
    const blocker = VT.trainingBlocker(status);
    const session = VT.heldSession(status);
    const gate = status.gate || {};
    const last = (gate.training || {}).last || null;
    const outliers = last && ownOutcome(last) ? VT.outlierLine(last) : null;
    if (blocker) nodes.push(line(blocker, "warn"));
    if (session && !blocker) {
      nodes.push(line(session.line, "warn"));
      const row = node("div", "row");
      row.append(
        button("Carry on", () => {
          const p = VT.trainingPlan(status, { add: session.add, held: session.rounds });
          train.heldOnServer = true;
          if (!p.rounds.length) finishOnly(Math.max(...session.rounds), session.add);
          else startPlan(p);
        }),
        button("Delete them", () => cancelTraining(), { ghost: true }),
      );
      nodes.push(row);
    } else if (!blocker) {
      if (outliers) {
        nodes.push(line(outliers, "warn"));
        if (last.outcome === "enrolled") {
          const row = node("div", "row");
          row.append(button("Record those again", () => startPlan(VT.outlierPlan(status, last.outliers))));
          nodes.push(row);
        }
      }
      const plan0 = VT.trainingPlan(status);
      const where = plan0.legacy ? "" : VT.strictnessOf(status) === "balanced"
        ? "The voice check is balanced: "
        : "The voice check is very strict: ";
      nodes.push(line(`${where}${VT.planLine(plan0)}`, "", "note"));
      const desktop = ((gate.prints || {}).desktop) || {};
      const row = node("div", "row");
      row.append(button("Train my voice", () => startPlan(VT.trainingPlan(status)), { id: "vt-start" }));
      if (desktop.trained === true && !desktop.needs_retraining && VT.understands(status).rounds) {
        row.append(button("Train more", () => startPlan(VT.trainingPlan(status, { add: true })), { ghost: true, id: "vt-more" }));
      }
      nodes.push(row);
    }
  }
  box.replaceChildren(...nodes);
}

/* ==========================================================================
   How strict, and private answers
   ========================================================================== */

let settingBusy = false;

function paintSettings() {
  const view = VT.settingsView(status);
  const wrap = $("vt-settings");
  if (!wrap) return;
  wrap.hidden = !view;
  if (!view) return;
  const group = (box, list, chosen, setting, disabled) => {
    box.replaceChildren(...list.map((c) => {
      const b = node("button", "choice", VT.choiceText(c));
      b.type = "button";
      b.dataset.value = c.id;
      b.setAttribute("aria-pressed", String(c.id === chosen));
      b.disabled = settingBusy || (disabled && disabled(c));
      b.addEventListener("click", () => changeSetting(setting, c.id, chosen));
      return b;
    }));
  };
  group($("vt-strictness"), VT.STRICTNESS, view.strictness, "strictness");
  group($("vt-privacy"), VT.PRIVACY, view.privacy, "privacy",
    (c) => c.id === "voice_is_enough" && !view.voiceIsEnoughAllowed && view.privacy !== "voice_is_enough");
  say($("vt-strictness-note"), VT.STRICTNESS.find((c) => c.id === view.strictness).detail);
  let privacyNote = VT.PRIVACY.find((c) => c.id === view.privacy).detail;
  if (!view.voiceIsEnoughAllowed) privacyNote += ` ${VT.VOICE_IS_ENOUGH_NOTE}`;
  say($("vt-privacy-note"), privacyNote);
  const memBox = $("vt-memory-box");
  if (memBox) {
    memBox.hidden = !view.memory;
    if (view.memory) {
      // "Voice check is enough" reads these aloud already: neither choice
      // would change anything, so neither can be pressed.
      const moot = VT.memoryMoot(view);
      group($("vt-memory"), VT.MEMORY, view.memory, "memory", () => moot);
      say($("vt-memory-note"), moot ? VT.MEMORY_MOOT_NOTE : VT.MEMORY.find((c) => c.id === view.memory).detail);
    }
  }
  // Decision 13: answers that use a sensitive saved fact. Offered only when
  // the PC reports the setting, and never moot - it holds even under
  // "Voice check is enough". "Read aloud" is held on a stale link
  // (changeSetting, VT.loosens), like every loosening.
  const sensBox = $("vt-sensitive-box");
  if (sensBox) {
    sensBox.hidden = !view.sensitiveMemory;
    if (view.sensitiveMemory) {
      group($("vt-sensitive"), VT.SENSITIVE_MEMORY, view.sensitiveMemory, "sensitive_memory");
      let sensitiveNote = VT.SENSITIVE_MEMORY.find((c) => c.id === view.sensitiveMemory).detail;
      if (VT.sensitiveCovered(view)) sensitiveNote += ` ${VT.SENSITIVE_COVERED_NOTE}`;
      say($("vt-sensitive-note"), sensitiveNote);
    }
  }
  // The fifth: how far "Hey Jarvis" is trusted (the owner's decision,
  // 2026-09-24). Offered only when the PC reports it. "Only trust the talk
  // button" applies at once; "Same as the talk button" is the looser one,
  // held on a stale link (changeSetting, VT.loosens).
  const handsBox = $("vt-handsfree-box");
  if (handsBox) {
    handsBox.hidden = !view.handsFree;
    if (view.handsFree) {
      group($("vt-handsfree"), VT.HANDS_FREE, view.handsFree, "hands_free");
      say($("vt-handsfree-note"), VT.HANDS_FREE.find((c) => c.id === view.handsFree).detail);
    }
  }
  const waiting = VT.settingWaitingLine(view.waiting, APPROVE_WHERE);
  const w = $("vt-setting-waiting");
  w.hidden = !waiting;
  w.textContent = waiting || "";
}

async function changeSetting(setting, value, current) {
  if (settingBusy || value === current) return;
  const out = $("vt-setting-status");
  if (VT.loosens(setting, value) && linkStale) {
    say(out, HELD, "bad");
    announce(HELD, "assertive");
    return;
  }
  settingBusy = true;
  paintSettings();
  say(out, VT.loosens(setting, value) ? "Asking…" : "Changing it…");
  try {
    const answer = await invoke("set_voice_setting", { setting, value });
    const reply = VT.settingReply(answer, APPROVE_WHERE);
    say(out, reply.text, reply.tone);
    announce(reply.text, reply.tone === "bad" ? "assertive" : "polite");
  } catch (error) {
    say(out, problemWords(error), "bad");
    announce(out.textContent, "assertive");
  } finally {
    settingBusy = false;
  }
  // The choice shows what Jarvis says, never what was clicked.
  await reload();
}

/* ==========================================================================
   How often Jarvis asks you to repeat, and the guided test
   ========================================================================== */

const test = { view: "idle", lines: null, tone: "" };

function paintRepeat() {
  const list = $("vt-repeat");
  if (!list) return;
  const lines = VT.repeatLines(status);
  list.replaceChildren(...lines.map((l) => {
    const li = node("li", "sc-gpu", l.text);
    li.dataset.kind = l.id;
    if (l.tone) li.dataset.tone = l.tone;
    return li;
  }));
  const note = $("vt-repeat-note");
  note.hidden = !lines.length || lines[0].id === "none";
  note.textContent = VT.REPEAT_NOTE;
}

function testBlocker() {
  const can = VT.understands(status);
  if (!can.measure) return "This PC's Jarvis cannot run the test yet. Update the backend by running apply-patches.ps1.";
  const gate = status.gate || {};
  const prints = gate.prints || {};
  const trained = ["desktop", "phone", "general"].some((k) => prints[k] && prints[k].trained === true);
  if (!trained) return "Train your voice first; the test checks your voice against what Jarvis learned.";
  const models = gate.models;
  if (models && typeof models === "object" && !models.very_strict_model) {
    return "No voice-ID model is installed, so there is nothing to test yet.";
  }
  return null;
}

function paintTest() {
  const box = $("vt-test");
  if (!box || !status) return;
  if (test.view === "reading") return;
  const nodes = [];
  if (test.view === "result") {
    for (const text of test.lines || []) nodes.push(line(text, test.tone === "bad" ? "bad" : ""));
    const row = node("div", "row");
    row.append(button("Done", () => { test.view = "idle"; paintTest(); }));
    nodes.push(row);
    box.replaceChildren(...nodes);
    return;
  }
  const lastTest = ((status.gate || {}).training || {}).measure_last;
  const lastLines = lastTest ? VT.measureLines(lastTest) : null;
  if (lastLines) {
    nodes.push(line("The last guided test:", "", "vt-head"));
    for (const text of lastLines) nodes.push(line(text, ""));
  }
  nodes.push(line(VT.TEST_INTRO, "", "note"));
  const blocker = testBlocker();
  if (blocker) nodes.push(line(blocker, "warn"));
  const row = node("div", "row");
  row.append(button("Start the test", () => startTest(), { disabled: Boolean(blocker), id: "vt-test-start" }));
  nodes.push(row);
  box.replaceChildren(...nodes);
}

function startTest() {
  test.view = "reading";
  const max = VT.limits(status).measureMax;
  const items = VT.TEST_SENTENCES.slice(0, max).map((text, i) => ({ slot: `m${i}`, text }));
  makeReader($("vt-test"), {
    items,
    head: "The guided test",
    maxSeconds: VT.limits(status).maxSeconds - 0.2,
    sendLabel: "Check them",
    sendNote: "Nothing is saved and no card is raised.",
    cardSend: false,
    onSend: async (slots) => {
      const answer = await invoke("measure_voice", { slots });
      const reply = VT.measureReply(answer);
      if (reply.tone === "ok") {
        test.view = "result";
        test.lines = reply.lines;
        test.tone = "ok";
        paintTest();
        reload();
        return { ok: true, text: reply.lines[0], tone: "ok" };
      }
      return { ok: false, text: reply.lines[0], tone: "bad" };
    },
    onCancel: () => {
      cancelRecording();
      invoke("discard_voice_samples", { prefix: "m" }).catch(() => {});
      test.view = "idle";
      paintTest();
    },
  });
}

/* ==========================================================================
   The "someone else" check, and the stricter bar it may suggest
   ========================================================================== */

/** `view`: "idle", "reading" (the reader draws) or "result". */
const others = { view: "idle", result: null, proposing: false, note: "", tone: "" };

function paintOthers() {
  const box = $("vt-others");
  const head = $("vt-others-head");
  if (!box || !head || !status) return;
  if (others.view === "reading") return;
  // Offered only to a PC that understands it: an older one would read the
  // other person's clips as a training (VT.canCheck).
  const shown = others.view === "result" || VT.canCheck(status);
  box.hidden = !shown;
  head.hidden = !shown;
  if (!shown) return;
  const nodes = [];
  if (others.view === "result" && others.result) {
    const r = others.result;
    nodes.push(line("Someone else's voice", "", "vt-head"));
    const said = line(r.text, r.ok ? "" : "bad", "sc-line vt-others-result");
    said.setAttribute("role", "status");
    nodes.push(said);
    if (r.suggested !== null) {
      const row = node("div", "row");
      // The card is held on a stale link (rule 4); the check was not.
      row.append(button(`Use ${VT.score(r.suggested)} (asks for approval)`, () => proposeStricter(),
        { disabled: others.proposing || linkStale, id: "vt-others-use" }));
      nodes.push(row);
      nodes.push(line(VT.CHECK_CARD_NOTE, "", "note"));
      const why = others.note || (linkStale ? HELD : "");
      if (why) {
        const p = line(why, others.note ? others.tone : "warn", "sc-line vt-others-note");
        p.setAttribute("role", "status");
        nodes.push(p);
      }
    }
    const row = node("div", "row");
    row.append(button("Done", () => {
      others.view = "idle";
      others.result = null;
      others.note = "";
      paintOthers();
    }, { ghost: true }));
    nodes.push(row);
  } else {
    nodes.push(line(VT.CHECK_INTRO, "", "note"));
    const row = node("div", "row");
    row.append(button("Start the check", () => startOthers(), { id: "vt-others-start" }));
    nodes.push(row);
  }
  box.replaceChildren(...nodes);
}

function startOthers() {
  others.view = "reading";
  others.result = null;
  others.note = "";
  const box = $("vt-others");
  const toResult = (result) => {
    others.view = "result";
    others.result = result;
    paintOthers();
  };
  makeReader(box, {
    items: VT.OTHER_SENTENCES.map((text, i) => ({ slot: `o${i}`, text })),
    head: "Someone else's voice: ask them to read these",
    maxSeconds: VT.limits(status).maxSeconds - 0.2,
    sendLabel: "Compare them",
    sendNote: "Their recordings are scored on your PC and thrown away. Nothing changes and no card is raised.",
    // Nothing changes and no card is raised, so a stale link does not hold it.
    cardSend: false,
    onSend: async (slots) => {
      let result;
      try {
        result = VT.checkResult(await invoke("check_voice_with_someone_else", { slots }));
      } catch (error) {
        // The recordings are gone either way (the app drops them), so the
        // reader cannot send them again: the result view says what happened.
        result = { ok: false, text: problemWords(error), suggested: null, model: "" };
      }
      toResult(result);
      return { ok: true, text: result.text, tone: result.ok ? "ok" : "bad" };
    },
    onCancel: () => {
      cancelRecording();
      invoke("discard_voice_samples", { prefix: "o" }).catch(() => {});
      others.view = "idle";
      paintOthers();
    },
  });
}

async function proposeStricter() {
  const r = others.result;
  if (!r || r.suggested === null || others.proposing) return;
  if (linkStale) {
    others.note = HELD;
    others.tone = "bad";
    announce(HELD, "assertive");
    paintOthers();
    return;
  }
  others.proposing = true;
  others.note = "Asking…";
  others.tone = "";
  paintOthers();
  try {
    const answer = await invoke("propose_voice_threshold", { threshold: r.suggested, model: r.model || null });
    const reply = VT.thresholdReply(answer, APPROVE_WHERE);
    others.note = reply.text;
    others.tone = reply.tone;
  } catch (error) {
    others.note = problemWords(error);
    others.tone = "bad";
  } finally {
    others.proposing = false;
  }
  announce(others.note, others.tone === "bad" ? "assertive" : "polite");
  paintOthers();
  await reload();
}

/* ==========================================================================
   The voice-ID model, and the PC's own note
   ========================================================================== */

function paintModel() {
  const m = VT.modelLine(status);
  const p = $("vt-model");
  if (!p) return;
  p.hidden = !m;
  if (m) {
    $("vt-model-text").textContent = m.text;
    if (m.tone) p.dataset.tone = m.tone;
    else delete p.dataset.tone;
    const a = $("vt-model-link");
    a.hidden = !m.link;
    if (m.link) {
      a.href = m.link;
      a.textContent = m.linkText;
    }
  }
  const note = VT.noteLine(status);
  const n = $("vt-note");
  n.hidden = !note;
  n.textContent = note ? `Your PC says: ${note}` : "";
}

/** Settings' voice status arrived (or was re-read): draw everything from it. */
export function paintVoicePanel(voiceStatus) {
  status = voiceStatus && typeof voiceStatus === "object" ? voiceStatus : null;
  if (!status) return;
  paintModel();
  paintTrain();
  paintSettings();
  paintRepeat();
  paintTest();
  paintOthers();
}

/* ==========================================================================
   Jarvis's voice: custom voices
   ========================================================================== */

const cv = {
  card: $("voices"),
  state: $("cv-state"),
  body: $("cv-body"),
  status: null,
  seq: 0,
  busy: false,
  sentence: 0,
  way: "record",
  recording: null,
  file: null,
  fileData: null,
};

function cvStatusLine(reply) {
  say($("cv-status"), reply.text, reply.tone);
  const d = $("cv-status-detail");
  d.hidden = !reply.detail;
  d.textContent = reply.detail || "";
  announce(reply.text, reply.tone === "bad" ? "assertive" : "polite");
}

async function loadVoices() {
  if (!IS_TAURI || !cv.card) return;
  const seq = ++cv.seq;
  let answer;
  try {
    answer = await invoke("get_custom_voices");
  } catch (error) {
    if (seq !== cv.seq) return;
    cvProblem(`Jarvis could not be asked about its voices. ${problemWords(error)}`);
    return;
  }
  if (seq !== cv.seq) return;
  if (!answer || typeof answer !== "object" || answer.available === false || !Array.isArray(answer.voices)) {
    cvProblem(answer && typeof answer.why === "string" && answer.why ? answer.why
      : "This PC's Jarvis does not have custom voices yet. Update the backend by running apply-patches.ps1, then open this again.");
    return;
  }
  cv.status = answer;
  paintVoices();
}

function cvProblem(words) {
  cv.status = null;
  cv.body.hidden = true;
  cv.state.hidden = false;
  cv.state.dataset.tone = "bad";
  cv.state.textContent = words;
}

function paintVoices() {
  const st = cv.status;
  if (!st) return;
  cv.state.hidden = true;
  delete cv.state.dataset.tone;
  cv.body.hidden = false;
  say($("cv-speaking"), CV.speakingLine(st));
  const lineOr = (id, text) => {
    const p = $(id);
    p.hidden = !text;
    p.textContent = text || "";
  };
  lineOr("cv-fallback", CV.fallbackLine(st));
  lineOr("cv-pending", CV.pendingLine(st, APPROVE_WHERE));
  lineOr("cv-last", CV.lastLine(st));

  $("cv-list").replaceChildren(...CV.voiceRows(st).map((row) => {
    const li = node("li", "sc-gpu cv-voice");
    li.dataset.voice = row.id;
    if (row.tone) li.dataset.tone = row.tone;
    const label = node("label");
    const radio = document.createElement("input");
    radio.type = "radio";
    radio.name = "cv-active";
    radio.value = row.id;
    radio.checked = row.active;
    // Back to the built-in voice is always allowed, ready or not: it only
    // takes the custom voice away. A custom voice that cannot be used is not
    // offered.
    radio.disabled = cv.busy || (!row.ready && !row.builtin && !row.active);
    radio.addEventListener("change", () => chooseVoice(row));
    const text = node("span", "cv-text");
    text.append(node("span", "sc-gpu-name", row.name), node("span", "sc-gpu-role", row.detail));
    label.append(radio, text);
    li.append(label);
    if (!row.builtin) {
      const del = button("Delete", () => deleteVoice(row), { ghost: true, disabled: cv.busy });
      del.classList.add("small");
      del.setAttribute("aria-label", `Delete the voice ${row.name}`);
      li.append(del);
    }
    return li;
  }));

  $("cv-consent").textContent = CV.CONSENT;
  if (!$("cv-sentence").textContent) $("cv-sentence").textContent = CV.sentenceToRead(st, cv.sentence);
  paintAdd();

  const better = CV.betterView(st, APPROVE_WHERE);
  $("cv-better").hidden = !better.show;
  const sw = $("cv-better-switch");
  sw.checked = better.on || better.waiting;
  sw.disabled = cv.busy || better.waiting || (!better.on && !better.canTurnOn);
  $("cv-better-lines").replaceChildren(...better.lines.map((l) => {
    const p = node("p", l.tone === "waiting" ? "sc-waiting" : l.tone === "why" ? "sc-why" : "", l.text);
    return p;
  }));
  const why = $("cv-better-why");
  const reason = (st.better_voice || {}).why;
  why.hidden = better.show || !reason;
  why.textContent = reason ? `The better voice: ${CV.sentence(reason)}` : "";

  const timings = CV.timingLines(st);
  $("cv-timings").replaceChildren(...timings.map((t) => node("li", "sc-gpu", t)));
  $("cv-timings-none").hidden = timings.length > 0;
  paintSpeed();
}

/** "How fast Jarvis speaks": the PC's three choices, as radios. */
function paintSpeed() {
  const sp = CV.speedView(cv.status);
  $("cv-speed").hidden = !sp.show;
  if (!sp.show) return;
  $("cv-speed-title").textContent = sp.title;
  $("cv-speed-detail").textContent = sp.detail;
  const note = $("cv-speed-note");
  note.hidden = !sp.note;
  note.textContent = sp.note;
  $("cv-speed-choices").replaceChildren(...sp.choices.map((c) => {
    const row = node("label", "theme-row");
    row.dataset.choice = c.id;
    const radio = document.createElement("input");
    radio.type = "radio";
    radio.name = "cv-speed";
    radio.value = c.id;
    radio.checked = c.id === sp.choice;
    // Every change sent to the PC is held on a stale link (rule 4).
    radio.disabled = cv.busy || linkStale;
    radio.title = linkStale ? HELD : "";
    radio.addEventListener("change", () => {
      if (radio.checked) setSpeed(c.id);
    });
    const text = node("span", "theme-text");
    text.append(node("span", "theme-name", c.label));
    const tick = node("span", "theme-check", "✓");
    tick.setAttribute("aria-hidden", "true");
    row.append(radio, text, tick);
    return row;
  }));
}

async function setSpeed(speed) {
  const out = $("cv-speed-status");
  if (linkStale) {
    say(out, HELD, "bad");
    paintSpeed();
    return;
  }
  cv.busy = true;
  paintSpeed();
  say(out, "Sending…");
  try {
    const reply = CV.voiceReply(await invoke("set_voice_speed", { speed }), APPROVE_WHERE);
    say(out, reply.text, reply.tone);
    announce(reply.text);
  } catch (error) {
    say(out, problemWords(error), "bad");
    announce(out.textContent, "assertive");
  } finally {
    cv.busy = false;
  }
  await loadVoices();
}

function paintAdd() {
  const st = cv.status;
  if (!st) return;
  for (const b of $("cv-way").querySelectorAll("button")) {
    b.setAttribute("aria-pressed", String(b.dataset.value === cv.way));
  }
  $("cv-record").hidden = cv.way !== "record";
  $("cv-file-box").hidden = cv.way !== "file";
  const rec = $("cv-rec");
  rec.textContent = recorder.slot === "voice" ? "Stop" : cv.recording ? "Record again" : "Record";
  $("cv-another").disabled = recorder.slot === "voice";
  const blocker = CV.addBlocker({
    way: cv.way,
    name: $("cv-name").value,
    words: $("cv-words").value,
    recording: cv.recording,
    file: cv.file,
    linkBlocker: linkStale ? HELD : null,
    status: st,
  });
  $("cv-add").disabled = cv.busy || Boolean(blocker) || recorder.slot === "voice";
  const out = $("cv-add-status");
  if (!out.dataset.kept) say(out, blocker || "", blocker ? "" : "");
}

async function chooseVoice(row) {
  if (cv.busy || row.active) return;
  if (!row.builtin && linkStale) {
    cvStatusLine({ text: HELD, detail: "", tone: "bad" });
    paintVoices();
    return;
  }
  cv.busy = true;
  cvStatusLine({ text: row.builtin ? "Switching back…" : "Asking…", detail: "", tone: "" });
  try {
    const answer = await invoke("set_active_voice", { voice: row.id });
    cvStatusLine(CV.voiceReply(answer, APPROVE_WHERE));
  } catch (error) {
    cvStatusLine({ text: problemWords(error), detail: "", tone: "bad" });
  } finally {
    cv.busy = false;
  }
  // The list shows what Jarvis says, never what was clicked.
  await loadVoices();
  paintVoices();
}

async function deleteVoice(row) {
  if (cv.busy) return;
  if (!window.confirm(CV.deleteQuestion(row))) return;
  cv.busy = true;
  try {
    const answer = await invoke("delete_custom_voice", { voice: row.id });
    cvStatusLine(CV.voiceReply(answer, APPROVE_WHERE));
  } catch (error) {
    cvStatusLine({ text: problemWords(error), detail: "", tone: "bad" });
  } finally {
    cv.busy = false;
  }
  await loadVoices();
}

async function recordVoice() {
  const out = $("cv-rec-status");
  if (recorder.slot === "voice") {
    try {
      const taken = await stopRecording();
      cv.recording = { seconds: Number(taken.seconds) || 0, peak: Number(taken.peak) || 0 };
      say(out, `Recorded: ${VT.lengthLabel(cv.recording.seconds)}`, "ok");
    } catch (error) {
      cv.recording = null;
      say(out, problemWords(error), "bad");
    }
    $("cv-meter").hidden = true;
    paintAdd();
    return;
  }
  if (recorder.slot) return;
  const lim = CV.voiceLimits(cv.status);
  try {
    await startRecording("voice", lim.maxSeconds + 4, (level) => {
      $("cv-meter-fill").style.width = `${Math.round(level * 100)}%`;
    }, () => recordVoice());
    cv.recording = null;
    $("cv-meter").hidden = false;
    say(out, "Recording. Read the sentence, then press Stop.");
  } catch (error) {
    say(out, problemWords(error), "bad");
  }
  paintAdd();
}

function readFile(file) {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onerror = () => reject(new Error("That file could not be read."));
    reader.onload = () => {
      const bytes = new Uint8Array(reader.result);
      let bin = "";
      for (let i = 0; i < bytes.length; i += 0x8000) {
        bin += String.fromCharCode.apply(null, bytes.subarray(i, i + 0x8000));
      }
      resolve(btoa(bin));
    };
    reader.readAsArrayBuffer(file);
  });
}

async function addVoice() {
  if (cv.busy) return;
  const out = $("cv-add-status");
  const detail = $("cv-add-detail");
  const name = $("cv-name").value.trim();
  if (linkStale) {
    say(out, HELD, "bad");
    return;
  }
  cv.busy = true;
  out.dataset.kept = "1";
  say(out, "Checking it on your PC…");
  detail.hidden = true;
  let args;
  try {
    if (cv.way === "file") {
      const data = await readFile(cv.file.blob);
      args = { name, transcript: $("cv-words").value.trim(), file: data };
    } else {
      // The words are the sentence that was shown - nothing is transcribed.
      args = { name, transcript: $("cv-sentence").textContent.trim(), slot: "voice" };
    }
    const answer = await invoke("create_custom_voice", args);
    const reply = CV.voiceReply(answer, APPROVE_WHERE);
    say(out, reply.text, reply.tone);
    detail.hidden = !reply.detail;
    detail.textContent = reply.detail || "";
    announce(reply.text, reply.tone === "bad" ? "assertive" : "polite");
    if (reply.waiting) {
      cv.recording = null;
      $("cv-name").value = "";
      $("cv-words").value = "";
      $("cv-file").value = "";
      cv.file = null;
      say($("cv-rec-status"), "");
    }
  } catch (error) {
    say(out, problemWords(error), "bad");
    announce(out.textContent, "assertive");
  } finally {
    cv.busy = false;
  }
  await loadVoices();
  paintAdd();
}

async function setBetter(on) {
  const out = $("cv-better-status");
  if (on && linkStale) {
    say(out, HELD, "bad");
    paintVoices();
    return;
  }
  cv.busy = true;
  say(out, on ? "Asking…" : "Turning it off…");
  try {
    const answer = await invoke("set_better_voice", { enabled: on });
    const reply = CV.voiceReply(answer, APPROVE_WHERE);
    say(out, reply.text, reply.tone);
    announce(reply.text);
  } catch (error) {
    say(out, problemWords(error), "bad");
  } finally {
    cv.busy = false;
  }
  await loadVoices();
}

/** Wires the page. `opts.reload` re-reads GET /api/voice/status (settings.js). */
export function startVoicePanel(opts = {}) {
  if (typeof opts.reload === "function") reload = opts.reload;
  onLink((l) => {
    const was = linkStale;
    linkStale = Boolean(l && l.stale);
    if (was !== linkStale) {
      if (train.reader && train.view === "reading") train.reader.draw();
      if (others.view === "result") paintOthers();
      if (cv.status) {
        paintAdd();
        paintSpeed();
      }
    }
  });
  if (!cv.card) return;
  for (const b of $("cv-way").querySelectorAll("button")) {
    b.addEventListener("click", () => {
      cancelRecording();
      cv.way = b.dataset.value === "file" ? "file" : "record";
      paintAdd();
    });
  }
  $("cv-another").addEventListener("click", () => {
    cv.sentence += 1;
    cv.recording = null;
    say($("cv-rec-status"), "");
    $("cv-sentence").textContent = CV.sentenceToRead(cv.status, cv.sentence);
    paintAdd();
  });
  $("cv-rec").addEventListener("click", () => recordVoice());
  $("cv-add").addEventListener("click", () => addVoice());
  $("cv-name").addEventListener("input", () => { delete $("cv-add-status").dataset.kept; paintAdd(); });
  $("cv-words").addEventListener("input", () => { delete $("cv-add-status").dataset.kept; paintAdd(); });
  $("cv-file").addEventListener("change", () => {
    const f = $("cv-file").files && $("cv-file").files[0];
    cv.file = f ? { name: f.name, size: f.size } : null;
    cv.file && Object.defineProperty(cv.file, "blob", { value: f, enumerable: false });
    delete $("cv-add-status").dataset.kept;
    paintAdd();
  });
  $("cv-better-switch").addEventListener("change", (e) => setBetter(e.target.checked));

  // A voice card ends, a voice is deleted, the better voice goes off: the
  // `voices` doorbell. A waiting card has no event of its own for its
  // answer, so the queue changing re-reads too.
  onEvent((frame) => {
    if (frame && frame.kind === "voices") loadVoices();
  });
  onQueue(() => {
    const st = cv.status;
    if (st && (st.pending || (st.better_voice && st.better_voice.pending))) loadVoices();
  });
  document.addEventListener("visibilitychange", () => {
    if (!document.hidden) loadVoices();
  });
  // Closing the window drops what this page recorded (the app would drop
  // it after 30 minutes anyway). A round the PC already holds stays there,
  // so the training can be carried on.
  window.addEventListener("pagehide", () => {
    if (!IS_TAURI) return;
    invoke("cancel_voice_sample").catch(() => {});
    invoke("discard_voice_samples", {}).catch(() => {});
  });
  loadVoices();
}
