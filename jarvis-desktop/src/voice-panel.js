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
  // An animal's "Try it" still playing would be recorded with the owner.
  stopTry();
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
  // The sixth: answers about the screen after "Hey Jarvis" (the owner's
  // decision, 2026-09-28). Offered only when the PC reports it. It matters
  // only under "Only trust the talk button", and says so otherwise - the
  // choices stay usable. "Read aloud" is the looser one, held on a stale
  // link (changeSetting, VT.loosens).
  const screenBox = $("vt-screen-box");
  if (screenBox) {
    screenBox.hidden = !view.handsFreeScreen;
    if (view.handsFreeScreen) {
      group($("vt-screen"), VT.HANDS_FREE_SCREEN, view.handsFreeScreen, "hands_free_screen");
      let screenNote = VT.HANDS_FREE_SCREEN.find((c) => c.id === view.handsFreeScreen).detail;
      if (VT.screenCovered(view)) screenNote += ` ${VT.SCREEN_ONLY_WHEN_STRICT_NOTE}`;
      say($("vt-screen-note"), screenNote);
    }
  }
  // The seventh: Jarvis Live under "Only trust the talk button" (the
  // owner's answers, 2026-09-28). Three choices; a stricter one applies at
  // once, a looser one is the card, held on a stale link.
  const liveBox = $("vt-live-box");
  if (liveBox) {
    liveBox.hidden = !view.handsFreeLive;
    if (view.handsFreeLive) {
      group($("vt-live"), VT.HANDS_FREE_LIVE, view.handsFreeLive, "hands_free_live");
      let liveNote = VT.HANDS_FREE_LIVE.find((c) => c.id === view.handsFreeLive).detail;
      if (VT.liveCovered(view)) liveNote += ` ${VT.LIVE_ONLY_WHEN_STRICT_NOTE}`;
      say($("vt-live-note"), liveNote);
    }
  }
  // The eighth: when App lock ends Jarvis Live on this PC (the owner's
  // decision, 2026-09-28). "Only when Windows locks" is the looser one, the
  // card, held on a stale link.
  const endBox = $("vt-live-end-box");
  if (endBox) {
    endBox.hidden = !view.liveEnd;
    if (view.liveEnd) {
      group($("vt-live-end"), VT.LIVE_END, view.liveEnd, "live_end");
      say($("vt-live-end-note"),
        `${VT.LIVE_END.find((c) => c.id === view.liveEnd).detail} ${VT.LIVE_END_NOTE}`);
    }
  }
  // Talk-to-type on this PC (the owner's decision, 2026-09-27). Offered only
  // when the PC reports it. "On" is one approval card and is held on a stale
  // link (changeSetting, VT.loosens); "Off" is at once.
  const talkBox = $("vt-talktype-box");
  if (talkBox) {
    talkBox.hidden = !view.talkToType;
    if (view.talkToType) {
      group($("vt-talktype"), VT.TALK_TO_TYPE, view.talkToType, "talk_to_type");
      say($("vt-talktype-note"), VT.TALK_TO_TYPE.find((c) => c.id === view.talkToType).detail);
    }
  }
  // "Better voice" (2026-09-28): the second "hey Jarvis" check and the
  // voice-ID model. Offered only when the PC reports them. A choice that
  // needs something the PC does not have is greyed out, with the PC's own
  // words saying why (VT.blockedWhy); the looser choice of each is held on
  // a stale link (changeSetting, VT.loosens).
  const better = [
    ["vt-wakeconfirm", VT.WAKE_CONFIRM, view.wakeConfirm, "wake_confirm"],
    ["vt-voiceid", VT.VOICE_ID_MODEL, view.voiceIdModel, "voice_id_model"],
  ];
  for (const [id, list, chosen, setting] of better) {
    const box = $(`${id}-box`);
    if (!box) continue;
    box.hidden = !chosen;
    if (!chosen) continue;
    group($(id), list, chosen, setting, (c) => Boolean(VT.blockedWhy(status, setting, c.id)));
    const blocked = list.map((c) => VT.blockedWhy(status, setting, c.id)).find(Boolean);
    const detail = list.find((c) => c.id === chosen).detail;
    say($(`${id}-note`), blocked ? `${detail} ${blocked}` : detail);
  }
  const waiting = VT.settingWaitingLine(view.waiting, APPROVE_WHERE);
  const w = $("vt-setting-waiting");
  w.hidden = !waiting;
  w.textContent = waiting || "";
}

async function changeSetting(setting, value, current) {
  if (settingBusy || value === current) return;
  const out = $("vt-setting-status");
  const loosening = VT.loosens(setting, value, current);
  if (loosening && linkStale) {
    say(out, HELD, "bad");
    announce(HELD, "assertive");
    return;
  }
  settingBusy = true;
  paintSettings();
  say(out, loosening ? "Asking…" : "Changing it…");
  try {
    // Jarvis Live's three choices: the Rust side needs the choice now to
    // tell a stricter move from a looser one.
    const args = setting === "hands_free_live" ? { setting, value, current } : { setting, value };
    const answer = await invoke("set_voice_setting", args);
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
  paintSpeaker();
  paintFace();
  paintAnimals();
}

/** "How fast Jarvis speaks": the PC's three choices, as radios. */
function paintSpeed() {
  paintChoiceRow(CV.speedView(cv.status), "cv-speed", setSpeed);
}

/** "Jarvis's built-in voice": the PC's choices, as radios - the same row
 * as speed, right next to it. */
function paintSpeaker() {
  paintChoiceRow(CV.speakerView(cv.status), "cv-speaker", setSpeaker, hearVoice);
}

/** The row both speed and the built-in-voice choice use: a title, a
 * detail line, radios for the PC's own choices, and an optional note.
 * `onHear(id, label, button)`: every choice also gets a "Hear it" button
 * (the built-in voices' samples) - a button beside the radio, not inside
 * it, so pressing it never changes the choice. */
function paintChoiceRow(view, prefix, onChoose, onHear = null) {
  $(prefix).hidden = !view.show;
  if (!view.show) return;
  $(`${prefix}-title`).textContent = view.title;
  $(`${prefix}-detail`).textContent = view.detail;
  const note = $(`${prefix}-note`);
  note.hidden = !view.note;
  note.textContent = view.note;
  $(`${prefix}-choices`).replaceChildren(...view.choices.map((c) => {
    const row = node("label", "theme-row");
    row.dataset.choice = c.id;
    const radio = document.createElement("input");
    radio.type = "radio";
    radio.name = prefix;
    radio.value = c.id;
    radio.checked = c.id === view.choice;
    // Every change sent to the PC is held on a stale link (rule 4).
    radio.disabled = cv.busy || linkStale;
    radio.title = linkStale ? HELD : "";
    radio.addEventListener("change", () => {
      if (radio.checked) onChoose(c.id);
    });
    const text = node("span", "theme-text");
    text.append(node("span", "theme-name", c.label));
    // The PC's one plain line under the name, when it has one (Ashby, Clara).
    if (c.detail) text.append(node("span", "theme-blurb", c.detail));
    const tick = node("span", "theme-check", "✓");
    tick.setAttribute("aria-hidden", "true");
    row.append(radio, text, tick);
    if (!onHear) return row;
    const wrap = node("div", "cv-choice");
    const hear = button(CV.HEAR_LABEL, () => onHear(c.id, c.label, hear), { ghost: true });
    hear.classList.add("small");
    hear.setAttribute("aria-label", `Hear ${c.label}`);
    hear.dataset.hear = c.id;
    // What happens when this voice's button is pressed is said right here,
    // beside the voice - not only below a long list.
    const rowStatus = node("span", "status cv-hear-status");
    rowStatus.setAttribute("role", "status");
    rowStatus.dataset.hearStatus = c.id;
    wrap.append(row, hear, rowStatus);
    return wrap;
  }));
}

/** "Voice follows the face": an on/off switch under the built-in voice,
 * with the PC's own line saying what is happening now. */
function paintFace() {
  const fv = CV.faceVoiceView(cv.status);
  $("cv-face").hidden = !fv.show;
  if (!fv.show) return;
  $("cv-face-title").textContent = fv.title;
  $("cv-face-detail").textContent = fv.detail;
  const line = $("cv-face-line");
  line.hidden = !fv.line;
  line.textContent = fv.line;
  const sw = $("cv-face-switch");
  sw.checked = fv.enabled;
  // Every change sent to the PC is held on a stale link (rule 4).
  sw.disabled = cv.busy || linkStale;
  sw.title = linkStale ? HELD : "";
  // The one-time "has its own voice. Use it?" question, in the PC's words.
  const offer = CV.faceOfferView(cv.status);
  $("cv-face-offer").hidden = !offer.show;
  if (!offer.show) return;
  $("cv-face-offer-question").textContent = offer.question;
  for (const [id, word, answer] of [["cv-face-offer-use", offer.use, "use"],
    ["cv-face-offer-keep", offer.keep, "keep"]]) {
    const b = $(id);
    b.textContent = word;
    b.dataset.face = offer.face;
    b.dataset.answer = answer;
    b.disabled = cv.busy || linkStale;
    b.title = linkStale ? HELD : "";
  }
}

/* Each animal's voice: one row per animal, built once and then updated in
   place, so a repaint never takes the keyboard focus off the slider or list
   the owner is using. A change is sent at once (no card); several quick
   changes to one animal are folded into the last one. */
const animals = { rows: new Map(), want: new Map(), sending: false, playing: null /* {audio, row} */ };

function animalRow(view, a) {
  const row = node("div", "cv-animal");
  row.dataset.face = a.face;
  const head = node("div", "cv-animal-head");
  const name = node("span", "cv-animal-name", a.name);
  const lineEl = node("span", "cv-animal-line");
  head.append(name, lineEl);

  const voiceField = node("label", "cv-animal-field");
  const voice = document.createElement("select");
  voice.setAttribute("aria-label", `${a.name}'s voice`);
  for (const v of view.voices) {
    const o = document.createElement("option");
    o.value = v.id;
    o.textContent = v.label;
    voice.append(o);
  }
  voiceField.append(node("span", "", "Voice"), voice);

  const pitchField = node("label", "cv-animal-field");
  const pitch = document.createElement("input");
  pitch.type = "range";
  pitch.setAttribute("aria-label", `${a.name}'s pitch`);
  const shown = node("output", "cv-animal-pitch");
  pitchField.append(node("span", "", "Pitch"), pitch, shown);

  const pace = node("div", "choices");
  pace.setAttribute("role", "group");
  pace.setAttribute("aria-label", `${a.name}'s pace`);
  for (const pc of view.paces) {
    const b = node("button", "choice", pc.label);
    b.type = "button";
    b.dataset.value = pc.id;
    pace.append(b);
  }

  const tryIt = button("Try it", () => tryAnimal(a.face), { ghost: true });
  tryIt.classList.add("small");
  tryIt.setAttribute("aria-label", `Try the ${a.name}'s voice`);
  const reset = button("Reset to its own voice", () => resetAnimal(a.face), { ghost: true });
  reset.classList.add("small");
  reset.setAttribute("aria-label", `Reset the ${a.name} to its own voice`);

  // Change your mind about the one-time question: only when it was answered.
  const mind = button("Keep my voice", () => {
    if (mind.dataset.answer) answerAnimalOffer(a.face, mind.dataset.answer, status);
  }, { ghost: true });
  mind.classList.add("small");
  mind.hidden = true;

  const controls = node("div", "cv-animal-controls");
  const status = node("span", "status");
  controls.append(voiceField, pitchField, pace, tryIt, reset, mind);
  status.setAttribute("role", "status");
  row.append(head, controls, status);

  const r = { row, lineEl, voice, pitch, shown, pace, tryIt, reset, mind, status, name: a.name };
  const current = () => ({
    speaker: voice.value,
    semitones: Number(pitch.value),
    pace: (pace.querySelector('[aria-pressed="true"]') || {}).dataset?.value || "normal",
  });
  voice.addEventListener("change", () => changeAnimal(a.face, current()));
  pitch.addEventListener("input", () => showPitch(r, Number(pitch.value)));
  pitch.addEventListener("change", () => changeAnimal(a.face, current()));
  for (const b of pace.querySelectorAll("button")) {
    b.addEventListener("click", () => {
      if (b.getAttribute("aria-pressed") === "true") return;
      for (const o of pace.querySelectorAll("button")) {
        o.setAttribute("aria-pressed", String(o === b));
      }
      changeAnimal(a.face, current());
    });
  }
  return r;
}

function showPitch(r, semis) {
  r.shown.textContent = CV.pitchShort(semis);
  r.pitch.setAttribute("aria-valuetext", CV.pitchWords(semis));
}

/** Each animal's voice: the PC's rows, with its own choices and words. */
function paintAnimals() {
  const view = CV.animalVoicesView(cv.status);
  const box = $("cv-animals");
  if (!box) return;
  box.hidden = !view.show;
  if (!view.show) return;
  $("cv-animals-title").textContent = view.title;
  const detail = $("cv-animals-detail");
  detail.hidden = !view.detail;
  detail.textContent = view.detail;
  const list = $("cv-animals-list");
  // The PC's list of voices or paces changed: build the rows again.
  const sig = JSON.stringify([view.voices, view.paces, view.pitch, view.animals.map((a) => a.face)]);
  if (list.dataset.sig !== sig) {
    animals.rows.clear();
    list.replaceChildren(...view.animals.map((a) => {
      const r = animalRow(view, a);
      animals.rows.set(a.face, r);
      return r.row;
    }));
    list.dataset.sig = sig;
  }
  for (const a of view.animals) {
    const r = animals.rows.get(a.face);
    if (!r) continue;
    r.lineEl.textContent = a.line;
    r.pitch.min = String(view.pitch.min);
    r.pitch.max = String(view.pitch.max);
    r.pitch.step = String(view.pitch.step);
    // A change on its way: leave what the owner just set on screen.
    if (!animals.want.has(a.face) && !(animals.sending && animals.sending === a.face)) {
      r.voice.value = a.speaker;
      r.pitch.value = String(a.semitones);
      showPitch(r, a.semitones);
      for (const b of r.pace.querySelectorAll("button")) {
        b.setAttribute("aria-pressed", String(b.dataset.value === a.pace));
      }
    }
    // Every change sent to the PC is held on a stale link (rule 4). Try it
    // changes nothing, so it is never held.
    for (const c of [r.voice, r.pitch, ...r.pace.querySelectorAll("button")]) {
      c.disabled = linkStale;
      c.title = linkStale ? HELD : "";
    }
    // "keep" offers its own voice; "use" offers going back; unanswered: neither.
    r.mind.hidden = !a.answer;
    r.mind.dataset.answer = a.answer === "keep" ? "use" : a.answer === "use" ? "keep" : "";
    r.mind.textContent = a.answer === "keep" ? "Use its own voice" : "Keep my voice";
    r.mind.setAttribute("aria-label", a.answer === "keep"
      ? `Use the ${a.name}'s own voice` : `Keep my voice for the ${a.name}`);
    r.mind.disabled = linkStale;
    r.mind.title = linkStale ? HELD : "";
    r.reset.disabled = linkStale || !a.changed;
    r.reset.title = linkStale ? HELD : a.changed ? "" : `The ${a.name} already speaks in its own voice.`;
  }
}

function changeAnimal(face, choice) {
  sendAnimal(face, { face, ...choice });
}

function resetAnimal(face) {
  sendAnimal(face, { face, reset: true });
}

/** Sends one animal's change - the newest one, if several came quickly. */
async function sendAnimal(face, args) {
  const r = animals.rows.get(face);
  if (linkStale) {
    if (r) say(r.status, HELD, "bad");
    paintAnimals();
    return;
  }
  animals.want.set(face, args);
  if (animals.sending) return;
  try {
    while (animals.want.size) {
      const [f, a] = animals.want.entries().next().value;
      animals.want.delete(f);
      animals.sending = f;
      const out = (animals.rows.get(f) || {}).status;
      say(out, "Sending…");
      try {
        const reply = a.reset
          ? await invoke("reset_voice_animal", { face: f })
          : await invoke("set_voice_animal", {
            face: f, speaker: a.speaker, semitones: a.semitones, pace: a.pace,
          });
        const words = CV.voiceReply(reply, APPROVE_WHERE);
        say(out, words.text, words.tone);
        announce(words.text, words.tone === "bad" ? "assertive" : "polite");
      } catch (error) {
        say(out, problemWords(error), "bad");
        announce(out ? out.textContent : problemWords(error), "assertive");
      }
    }
  } finally {
    animals.sending = false;
  }
  await loadVoices();
}

/*
 * Is Jarvis talking or listening? "Try it" must never play over a real
 * answer, and the microphone must never hear it. The phone asks its own
 * voice session (VoiceSession.tryAnimalVoice); this window plays no voice
 * of Jarvis's, so it is told by the events every window hears:
 *  - `face-voice`: the Jarvis bar is playing a spoken answer (a clock at
 *    least every 250 ms while it plays, face-voice.js `followClip`);
 *  - `voice-capture-started`: the talk button just opened the microphone
 *    (voice.rs `start_voice_capture`; the Rust also refuses "Try it" while
 *    the talk button records);
 *  - `voice-speech-started` / `voice-heard`: "hey Jarvis" heard a question;
 *  - `stop-everything`: the hotkey - every sound stops;
 *  - the link's `activity` (listening, thinking, working, speaking): a
 *    question is being answered - not trusted on a stale link, where it is
 *    only the last thing heard.
 */
const voiceNow = { speakingUntil: 0, activity: "idle", stale: true };
const TURN_ACTIVITY = ["listening", "thinking", "working", "speaking"];
/** How long one `face-voice` clock counts as "still playing". */
const SPEAKING_HOLD_MS = 1000;

function jarvisBusy() {
  if (Date.now() < voiceNow.speakingUntil) return true;
  return !voiceNow.stale && TURN_ACTIVITY.includes(voiceNow.activity);
}

/** Stops a "Try it" clip that is playing; its row then says `why`. */
function stopTry(why = "") {
  const p = animals.playing;
  if (!p) return;
  animals.playing = null;
  p.audio.pause();
  if (p.restore) p.restore();
  say(p.row.status, why);
}

/** "Try it": the PC says one fixed line in that animal's voice as it is now. */
async function tryAnimal(face) {
  const r = animals.rows.get(face);
  if (!r) return;
  await playFromPc({
    command: "try_voice_animal",
    args: { face },
    statusEl: r.status,
    button: r.tryIt,
    busyWords: CV.TRY_BUSY,
    playingWords: CV.tryPlaying(r.name),
    doneWords: CV.tryDone(r.name),
    // A change still on its way is heard, not the one before it.
    beforeAsk: async () => {
      for (let i = 0; i < 100 && (animals.sending || animals.want.size); i += 1) {
        await new Promise((ok) => setTimeout(ok, 50));
      }
    },
  });
}

/**
 * "Hear it" (2026-09-29): the PC says one fixed line in one built-in voice,
 * by name, and the voice Jarvis uses does not change. The same play-it-here
 * rules as "Try it": never over Jarvis, stopped the moment a question or an
 * answer starts, nothing held on a stale link (it changes nothing).
 */
async function hearVoice(voice, label, hearButton) {
  // The button reads "Stop" while its sample plays; pressing it stops the sample.
  if (hearButton.dataset.playing === "1") {
    stopTry(CV.HEAR_STOPPED);
    return;
  }
  // The words go beside the tapped voice; every other voice's line is cleared.
  for (const other of document.querySelectorAll("#cv-speaker-choices .cv-hear-status")) say(other, "");
  say($("cv-speaker-status"), "");
  await playFromPc({
    command: "hear_voice_sample",
    args: { voice },
    statusEl: hearButton.parentElement.querySelector(".cv-hear-status") || $("cv-speaker-status"),
    button: hearButton,
    whilePlaying: CV.HEAR_STOP,
    busyWords: CV.HEAR_BUSY,
    playingWords: CV.hearPlaying(label),
    doneWords: CV.hearDone(label),
  });
}

/**
 * Asks the PC for one short sound (`command` returns it as a data URI) and
 * plays it in this window - "Try it" and "Hear it" both. One at a time: what
 * was playing stops first. `busyWords` are said instead when Jarvis is talking
 * or listening, before asking and again after the PC answered.
 */
async function playFromPc({ command, args, statusEl, button: askButton, busyWords, playingWords, doneWords, beforeAsk, whilePlaying }) {
  stopTry();
  if (jarvisBusy()) {
    say(statusEl, busyWords, "bad");
    return;
  }
  askButton.disabled = true;
  say(statusEl, CV.TRY_ASKING);
  try {
    if (beforeAsk) await beforeAsk();
    const reply = await invoke(command, args);
    if (!reply || typeof reply.audio !== "string" || !reply.audio.startsWith("data:audio/")) {
      const words = CV.voiceReply(reply, APPROVE_WHERE);
      say(statusEl, words.tone === "bad" ? words.text : "The PC sent no sound.", "bad");
      return;
    }
    // Asked again: the PC took a moment, and a question may have begun.
    if (jarvisBusy()) {
      say(statusEl, busyWords, "bad");
      return;
    }
    const audio = new Audio(reply.audio);
    const mine = () => animals.playing && animals.playing.audio === audio;
    // A button that says "Stop" while it plays, and goes back after.
    const before = askButton.textContent;
    const restore = () => {
      if (!whilePlaying) return;
      askButton.textContent = before;
      delete askButton.dataset.playing;
    };
    animals.playing = { audio, row: { status: statusEl }, restore };
    if (whilePlaying) {
      askButton.textContent = whilePlaying;
      askButton.dataset.playing = "1";
    }
    say(statusEl, playingWords, "ok");
    audio.addEventListener("ended", () => {
      if (!mine()) return;
      animals.playing = null;
      restore();
      say(statusEl, doneWords, "ok");
    });
    try {
      await audio.play();
    } catch (error) {
      if (mine()) {
        animals.playing = null;
        restore();
      }
      throw error;
    }
  } catch (error) {
    say(statusEl, problemWords(error), "bad");
  } finally {
    askButton.disabled = false;
  }
}

/** Follows whether Jarvis is talking or listening (see `voiceNow`). */
function followJarvisVoice() {
  onLink((l) => {
    voiceNow.stale = Boolean(!l || l.stale);
    const was = voiceNow.activity;
    voiceNow.activity = String((l && l.activity) || "idle");
    if (!voiceNow.stale && was !== voiceNow.activity && TURN_ACTIVITY.includes(voiceNow.activity)) {
      stopTry(CV.TRY_STOPPED);
    }
  });
  if (!IS_TAURI || !TAURI.event || typeof TAURI.event.listen !== "function") return;
  const listen = (name, fn) => TAURI.event.listen(name, (event) => fn(event && event.payload));
  listen("face-voice", (cue) => {
    if (cue && cue.playing === true && cue.end !== true) {
      voiceNow.speakingUntil = Date.now() + SPEAKING_HOLD_MS;
      stopTry(CV.TRY_STOPPED);
    } else if (cue && (cue.end === true || cue.playing === false)) {
      voiceNow.speakingUntil = 0;
    }
  });
  for (const name of ["voice-capture-started", "voice-speech-started", "voice-heard"]) {
    listen(name, () => stopTry(CV.TRY_STOPPED));
  }
  listen("stop-everything", () => stopTry());
}

async function setSpeed(speed) {
  await sendChoice("cv-speed-status", "set_voice_speed", { speed }, [paintSpeed]);
}

async function setSpeaker(speaker) {
  await sendChoice("cv-speaker-status", "set_voice_speaker", { speaker }, [paintSpeaker]);
}

async function setFaceVoice(enabled) {
  await sendChoice("cv-face-status", "set_voice_face", { enabled }, [paintFace]);
}

/** The owner's answer to the one-time animal voice question. */
async function answerFaceOffer(button) {
  const { face, answer } = button.dataset;
  if (!face || !answer) return;
  await sendChoice("cv-face-status", "answer_face_voice_offer", { face, answer }, [paintFace]);
}

/** Changing the answer to the one-time question, from the animal's own row. */
async function answerAnimalOffer(face, answer, statusEl) {
  await sendChoice(statusEl, "answer_face_voice_offer", { face, answer }, [paintAnimals]);
}

async function sendChoice(statusId, command, args, repaint) {
  const out = typeof statusId === "string" ? $(statusId) : statusId;
  if (linkStale) {
    say(out, HELD, "bad");
    repaint.forEach((fn) => fn());
    return;
  }
  cv.busy = true;
  repaint.forEach((fn) => fn());
  say(out, "Sending…");
  try {
    const reply = CV.voiceReply(await invoke(command, args), APPROVE_WHERE);
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
        paintSpeaker();
        paintFace();
        paintAnimals();
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
  $("cv-face-switch").addEventListener("change", (e) => setFaceVoice(e.target.checked));
  $("cv-face-offer-use").addEventListener("click", (e) => answerFaceOffer(e.currentTarget));
  $("cv-face-offer-keep").addEventListener("click", (e) => answerFaceOffer(e.currentTarget));

  followJarvisVoice();

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
