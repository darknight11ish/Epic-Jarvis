/**
 * The voice flow in the Jarvis bar (docs/JARVIS-API.md section 17;
 * src/voice-flow.js, main.js; voice_flow.rs sends the clip).
 *
 * Interrupting by talking - pause first, decide second: half a second of
 * speech heard over a reply (voice.rs `voice-barge-onset`) PAUSES it at
 * once and asks for the clip to be checked (`judge_barge_in`). The PC's
 * answer (`voice-barge-verdict`): stop for good - a sentence made ahead is
 * dropped, never played - or carry on from where it paused. No answer
 * within 4 s: carry on. The first 3 s of a reply are ignored (echo).
 *
 * "One moment.": played when a tool starts during a spoken question, once
 * per question, before the reply's first sound and never over it.
 *
 * "I heard you": a small sound when the owner's turn is cut, with its own
 * switch, "Play a short sound when I finish speaking", on by default.
 *
 * The rules themselves are held to tests/fixtures/voice-flow-cases.json,
 * which the phone's VoiceFlowTest.kt reads too.
 */
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";
import * as K from "./uikit.mjs";
import * as F from "../src/voice-flow.js";

const HERE = dirname(fileURLToPath(import.meta.url));
const CASES = JSON.parse(readFileSync(join(HERE, "fixtures", "voice-flow-cases.json"), "utf8"));

const fails = [];
const check = async (name, fn) => {
  try { await fn(); console.log(`ok    ${name}`); }
  catch (e) { fails.push(name); console.log(`FAIL  ${name}\n      ${e.message}`); }
};

/* ── The rules, against the cases both apps share ───────────────────── */

await check("the numbers are the shared ones", async () => {
  const n = CASES.numbers;
  assert.equal(F.GRACE_MS, n.grace_ms);
  assert.equal(F.ONSET_MS, n.onset_ms);
  assert.equal(F.CLIP_MS, n.clip_ms);
  assert.equal(F.WAIT_MAX_MS, n.wait_max_ms);
  // voice_flow.rs holds the listener's half to the same two numbers.
  const rs = readFileSync(join(HERE, "..", "src-tauri", "src", "voice_flow.rs"), "utf8");
  assert.match(rs, new RegExp(`BARGE_ONSET: Duration = Duration::from_millis\\(${n.onset_ms}\\)`));
  assert.match(rs, new RegExp(`BARGE_CLIP: Duration = Duration::from_millis\\(${n.clip_ms}\\)`));
});

await check("interrupting: every shared case, step by step", async () => {
  for (const c of CASES.interrupt) {
    const flow = F.createInterruptFlow();
    c.steps.forEach((s, i) => {
      let got;
      if (s.do === "reply_started") got = (flow.replyStarted(s.at), undefined);
      else if (s.do === "reply_ended") got = (flow.replyEnded(), undefined);
      else if (s.do === "onset") got = flow.onset(s.at, s.id, s.allowed);
      else if (s.do === "verdict") got = flow.verdict(s.id, s.stop);
      else if (s.do === "tick") got = flow.tick(s.at);
      else throw new Error(`unknown step ${s.do}`);
      if ("expect" in s) assert.equal(got, s.expect, `${c.name}, step ${i + 1} (${s.do})`);
    });
  }
});

await check("\"One moment.\": every shared case", async () => {
  for (const c of CASES.moment) {
    const flow = F.createMomentFlow();
    c.steps.forEach((s, i) => {
      let got;
      if (s.do === "turn_started") flow.turnStarted();
      else if (s.do === "turn_ended") flow.turnEnded();
      else if (s.do === "reply_started") flow.replyStarted();
      else if (s.do === "stopped") flow.stopped();
      else if (s.do === "tool_started") got = flow.toolStarted(s.enabled, s.ready);
      else throw new Error(`unknown step ${s.do}`);
      if ("expect" in s) assert.equal(got, s.expect, `${c.name}, step ${i + 1} (${s.do})`);
    });
  }
  assert.equal(F.isToolStart({ phase: "tool_started", tool: "email_read" }), true);
  assert.equal(F.isToolStart({ phase: "tool_finished" }), false);
  assert.equal(F.isToolStart(null), false);
});

await check("\"I heard you\": the shared numbers, tiny and quiet", async () => {
  const h = CASES.heard_sound;
  assert.equal(F.HEARD_SOUND.rate, h.rate);
  assert.deepEqual(F.HEARD_SOUND.tones.map((t) => [t.hz, t.ms]), h.tones.map((t) => [t.hz, t.ms]));
  assert.equal(F.HEARD_SOUND.gapMs, h.gap_ms);
  assert.equal(F.HEARD_SOUND.fadeMs, h.fade_ms);
  assert.equal(F.HEARD_SOUND.gain, h.gain);
  const s = F.heardSoundSamples();
  assert.equal(s.length, h.samples);
  const peak = Math.max(...s.map(Math.abs));
  assert.ok(peak <= h.peak_at_most && peak > h.peak_at_most * 0.9, `peak ${peak}`);
  assert.equal(s[0], 0, "starts from silence (a fade, no click)");
  assert.equal(s[s.length - 1], 0, "ends in silence");
  const wav = F.wavBytes(s, h.rate);
  assert.equal(wav.length, 44 + 2 * h.samples);
  assert.equal(String.fromCharCode(...wav.slice(0, 4)), "RIFF");
  assert.match(F.heardSoundUri(), /^data:audio\/wav;base64,UklGR/);
});

await check("what the PC allows: an older PC (no flow block) allows nothing", async () => {
  const none = F.flowFromStatus(null);
  assert.equal(none.bargeIn, false);
  assert.equal(none.moment, false);
  assert.equal(F.flowFromStatus({ gate: {} }).bargeIn, false);
  const on = { flow: { available: true, barge_in: { enabled: true, available: true, why: "" },
    moment: { enabled: true, ready: true, key: "k1" } } };
  assert.deepEqual(F.flowFromStatus(on), { bargeIn: true, bargeInWhy: "", moment: true, momentReady: true, momentKey: "k1",
    afterQuestion: false, cutOff: false });
  const later = F.flowFromStatus({ flow: { ...on.flow, after_question: true, cut_off: true } });
  assert.equal(later.afterQuestion, true);
  assert.equal(later.cutOff, true);
  assert.equal(F.flowFromStatus({ flow: { ...on.flow, available: false, cut_off: true } }).cutOff, false);
  const cannot = { flow: { available: true, barge_in: { enabled: true, available: false, why: "no voice print" },
    moment: { enabled: false } } };
  assert.equal(F.flowFromStatus(cannot).bargeIn, false);
  assert.equal(F.flowFromStatus(cannot).bargeInWhy, "no voice print");
  assert.equal(F.flowFromStatus(cannot).moment, false);
  assert.equal(F.flowFromStatus({ flow: { ...on.flow, available: false } }).bargeIn, false);
});

await check("the \"One moment\" switch: on unless saved off, and its words", async () => {
  const mem = (v) => ({ getItem: () => v, setItem() {} });
  assert.equal(F.loadMoment(mem(null)), true);
  assert.equal(F.loadMoment(mem("off")), false);
  assert.equal(F.loadMoment({ getItem() { throw new Error("private"); } }), true);
  const store = new Map();
  const real = { getItem: (k) => store.get(k) ?? null, setItem: (k, v) => store.set(k, v) };
  assert.equal(F.saveMoment(false, real), true);
  assert.equal(F.loadMoment(real), false);
  assert.equal(F.MOMENT_NAME, "Say \"One moment\" if I'm kept waiting");
  assert.match(F.describeMoment(true), /^On: when Jarvis has to look something up/);
  assert.match(F.describeMoment(false), /^Off:/);
});

await check("the \"I heard you\" switch: on unless saved off, its own key, and its words", async () => {
  const mem = (v) => ({ getItem: () => v, setItem() {} });
  assert.equal(F.loadHeard(mem(null)), true);
  assert.equal(F.loadHeard(mem("off")), false);
  assert.equal(F.loadHeard(mem("on")), true);
  assert.equal(F.loadHeard({ getItem() { throw new Error("private"); } }), true);
  assert.equal(F.saveHeard(true, { setItem() { throw new Error("full"); } }), false);
  const store = new Map();
  const real = { getItem: (k) => store.get(k) ?? null, setItem: (k, v) => store.set(k, v) };
  assert.equal(F.saveHeard(false, real), true);
  assert.equal(F.loadHeard(real), false);
  assert.equal(F.loadMoment(real), true, "turning the sound off leaves \"One moment\" alone");
  assert.notEqual(F.HEARD_KEY, F.MOMENT_KEY);
  assert.equal(F.HEARD_NAME, "Play a short sound when I finish speaking");
  assert.match(F.describeHeard(true), /^On: a short two-note sound/);
  assert.match(F.describeHeard(false), /^Off:/);
});

/* ── The Jarvis bar ─────────────────────────────────────────────────── */

const { base, close } = await K.serve();
const browser = await K.launch();

const delta = (text) => JSON.stringify({ choices: [{ delta: { content: text } }] });
const step = (data) => ({ emit: "jarvis-event", payload: { kind: "step", id: 90, data } });
const filler = (n) => Array.from({ length: n }, () => delta(""));
const FLOW = {
  available: true,
  after_question: true,
  cut_off: true,
  barge_in: { enabled: true, available: true, why: "", min_seconds: 1.0, bar: "balanced", stop_word: true },
  moment: { enabled: true, text: "One moment.", key: "kokoro:af_heart:1.0", ready: true, after_ms: 1000, why: "" },
};
const MOMENT_URI = "data:audio/wav;base64,UklGRiQAAABXQVZFZm10IBAAAAABAAEAQB8AAEAfAAABAAgAZGF0YQAAAAA=#MOMENT";

/**
 * A quickbar whose speaker can be paused (each clip lasts `playMs` of
 * PLAYING time), whose clock can be moved on (`__skip`), whose PC answers
 * `get_voice_flow` with `flow`, and which counts the "I heard you" sounds.
 */
async function bar({ flow = FLOW, reply, playMs = 1500, heard = K.HEARD_OWNER, momentFails = false } = {}) {
  const page = await K.open(browser, base, "index.html", { heard, chatReplies: [reply] });
  await page.evaluate(({ flow, playMs, momentUri, momentFails }) => {
    const real = performance.now.bind(performance);
    let skew = 0;
    performance.now = () => real() + skew;
    window.__skip = (ms) => { skew += ms; };
    window.__flowCalls = [];
    const core = window.__TAURI__.core;
    const invoke = core.invoke;
    core.invoke = async (cmd, args) => {
      if (cmd === "get_voice_flow") { window.__flowCalls.push("flow"); return flow; }
      if (cmd === "get_voice_moment") {
        window.__flowCalls.push("moment");
        if (momentFails) throw new Error("switched off");
        return momentUri;
      }
      if (cmd === "judge_barge_in") { window.__flowCalls.push(`judge ${args.id}`); return null; }
      if (cmd === "speak_reply") {
        const out = await invoke(cmd, args);
        return typeof out === "string" ? `${out}#${encodeURIComponent(args.text)}` : out;
      }
      return invoke(cmd, args);
    };
    const said = (el) => decodeURIComponent(String(el.src).split("#")[1] || "");
    HTMLMediaElement.prototype.play = function () {
      const text = said(this);
      if (this.__left === undefined) this.__left = text === "MOMENT" ? 300 : playMs;
      window.__voiceCalls.push(["play", text]);
      this.__start = Date.now();
      this.__t = setTimeout(() => {
        this.__t = null;
        window.__voiceCalls.push(["end", text]);
        this.dispatchEvent(new Event("ended"));
      }, this.__left);
      return Promise.resolve();
    };
    HTMLMediaElement.prototype.pause = function () {
      if (!this.__t) return;
      clearTimeout(this.__t);
      this.__t = null;
      this.__left = Math.max(0, this.__left - (Date.now() - this.__start));
      window.__voiceCalls.push(["pause", said(this)]);
    };
    window.__heardSounds = 0;
    window.AudioContext = class {
      constructor() { this.state = "running"; this.destination = {}; }
      createBuffer(_c, n) { window.__heardLength = n; return { getChannelData: () => new Float32Array(n) }; }
      createBufferSource() { return { connect() {}, start() { window.__heardSounds += 1; } }; }
      resume() { return Promise.resolve(); }
    };
  }, { flow, playMs, momentUri: MOMENT_URI, momentFails });
  return page;
}

const log = (page) => page.evaluate(() => (window.__voiceCalls || [])
  .filter((c) => Array.isArray(c) && ["speak", "play", "end", "pause"].includes(c[0]))
  .map((c) => `${c[0]} ${c[1]}`));
const flowCalls = (page) => page.evaluate(() => window.__flowCalls.slice());
async function talk(page) {
  await page.hover("#mic");
  await page.mouse.down();
  await page.waitForTimeout(80);
  await page.mouse.up();
}
/** Waits until the log has `line`, or fails with the log. */
async function until(page, line, ms = 3000) {
  const end = Date.now() + ms;
  while (Date.now() < end) {
    if ((await log(page)).includes(line)) return;
    await page.waitForTimeout(25);
  }
  throw new Error(`never saw "${line}": ${JSON.stringify(await log(page))}`);
}
const onset = (page, id) => page.evaluate((id) => window.__emit("voice-barge-onset", { id }), id);
const verdict = (page, v) => page.evaluate((v) => window.__emit("voice-barge-verdict", v), v);
const skip = (page, ms) => page.evaluate((ms) => window.__skip(ms), ms);
const count = (lines, line) => lines.filter((l) => l === line).length;
async function done(page) {
  const errors = page.__errors;
  await page.close();
  assert.deepEqual(errors, []);
}

const TWO = [delta("One. "), delta("Two. ")];

await check("speech over the reply, past its first 3 s: paused at once, and the clip is asked about", async () => {
  const page = await bar({ reply: TWO });
  await talk(page);
  await until(page, "play One.");
  await skip(page, 3000);
  await onset(page, 5);
  await page.waitForTimeout(100);
  let lines = await log(page);
  assert.ok(lines.includes("pause One."), JSON.stringify(lines));
  assert.ok((await flowCalls(page)).includes("judge 5"));
  // Paused: the sentence does not play on while the PC decides.
  await page.waitForTimeout(1700);
  lines = await log(page);
  assert.ok(!lines.includes("end One."), JSON.stringify(lines));
  await done(page);
});

await check("the PC says it was the owner: stopped for good, and the sentence made ahead is dropped", async () => {
  const page = await bar({ reply: TWO });
  await talk(page);
  await until(page, "play One.");
  await until(page, "speak Two.");
  await skip(page, 3000);
  await onset(page, 5);
  await page.waitForTimeout(50);
  await verdict(page, { id: 5, stop: true, available: true, why: "owner_voice" });
  await page.waitForTimeout(1800);
  const lines = await log(page);
  assert.ok(lines.includes("speak Two."), `"Two." was made ahead: ${JSON.stringify(lines)}`);
  assert.ok(!lines.includes("play Two."), `a sound made ahead was played after stop: ${JSON.stringify(lines)}`);
  assert.equal(count(lines, "play One."), 1, JSON.stringify(lines));
  await done(page);
});

await check("the PC says it was not the owner: the reply carries on from where it paused", async () => {
  const page = await bar({ reply: TWO, playMs: 800 });
  await talk(page);
  await until(page, "play One.");
  await skip(page, 3000);
  await onset(page, 6);
  await page.waitForTimeout(300);
  await verdict(page, { id: 6, stop: false, available: true, why: "not_owner" });
  await until(page, "play Two.", 3000);
  const lines = await log(page);
  assert.equal(count(lines, "play One."), 2, `paused, then played on: ${JSON.stringify(lines)}`);
  assert.ok(lines.indexOf("pause One.") < lines.lastIndexOf("play One."));
  assert.ok(lines.includes("end One."));
  await done(page);
});

await check("no answer from the PC: after 4 s the reply carries on by itself", async () => {
  const page = await bar({ reply: TWO, playMs: 800 });
  await talk(page);
  await until(page, "play One.");
  await skip(page, 3000);
  await onset(page, 7);
  await page.waitForTimeout(3500);
  assert.equal(count(await log(page), "play One."), 1, "still paused before 4 s");
  await until(page, "end One.", 2500);
  assert.equal(count(await log(page), "play One."), 2);
  await done(page);
});

await check("the first 3 s of a reply are ignored (echo), and only while Jarvis talks", async () => {
  const page = await bar({ reply: TWO, playMs: 800 });
  await onset(page, 1); // nothing playing
  await talk(page);
  await until(page, "play One.");
  await onset(page, 2); // inside the grace period
  await page.waitForTimeout(100);
  let lines = await log(page);
  assert.ok(!lines.some((l) => l.startsWith("pause")), JSON.stringify(lines));
  assert.deepEqual((await flowCalls(page)).filter((c) => c.startsWith("judge")), []);
  await skip(page, 3000);
  await onset(page, 3);
  await page.waitForTimeout(100);
  lines = await log(page);
  assert.ok(lines.includes("pause One."), JSON.stringify(lines));
  assert.deepEqual((await flowCalls(page)).filter((c) => c.startsWith("judge")), ["judge 3"]);
  await done(page);
});

await check("an older PC, or one that cannot tell your voice, or the switch off: never paused, never asked", async () => {
  for (const [label, flow, off] of [
    ["no flow block", null, false],
    ["cannot tell the voice", { ...FLOW, barge_in: { ...FLOW.barge_in, available: false, why: "no voice print" } }, false],
    ["switch off", FLOW, true],
  ]) {
    const page = await bar({ reply: TWO, flow });
    if (off) await page.evaluate(() => localStorage.setItem("jarvis.voice.bargeIn", "off"));
    await talk(page);
    await until(page, "play One.");
    await skip(page, 3000);
    await onset(page, 9);
    await page.waitForTimeout(100);
    const lines = await log(page);
    assert.ok(!lines.some((l) => l.startsWith("pause")), `${label}: ${JSON.stringify(lines)}`);
    assert.deepEqual((await flowCalls(page)).filter((c) => c.startsWith("judge")), [], label);
    await done(page);
  }
});

await check("\"stop\" (the stop word) still stops inside the first 3 s", async () => {
  const page = await bar({ reply: TWO });
  await talk(page);
  await until(page, "play One.");
  await until(page, "speak Two.");
  await page.evaluate(() => window.__emit("voice-speech-started", null));
  await page.waitForTimeout(1800);
  const lines = await log(page);
  assert.ok(!lines.includes("play Two."), JSON.stringify(lines));
  await done(page);
});

await check("\"One moment.\": played when a tool starts, once, and the reply waits for it to end", async () => {
  const page = await bar({ reply: [...filler(20), step({ phase: "tool_started", tool: "calendar_read" }),
    step({ phase: "tool_finished", tool: "calendar_read", ok: true }),
    step({ phase: "tool_started", tool: "email_read" }), ...filler(20), delta("Found it. ")], playMs: 300 });
  await talk(page);
  await until(page, "play MOMENT");
  await page.waitForTimeout(1500);
  const lines = await log(page);
  assert.equal(count(lines, "play MOMENT"), 1, JSON.stringify(lines));
  // A tool ran, so the answer itself stays on screen (section 16).
  const next = lines.findIndex((l) => l.startsWith("play ") && l !== "play MOMENT");
  assert.ok(next > lines.indexOf("end MOMENT"), `never over the reply: ${JSON.stringify(lines)}`);
  assert.equal(lines[next], "play It's on your screen.", JSON.stringify(lines));
  await done(page);
});

await check("\"One moment.\": not once the reply has made a sound, not when switched off, not for a typed question", async () => {
  const late = await bar({ reply: [delta("Let me look. "), ...filler(40), step({ phase: "tool_started", tool: "email_read" })],
    playMs: 600 });
  await talk(late);
  await until(late, "play Let me look.");
  await late.waitForTimeout(800);
  assert.ok(!(await log(late)).includes("play MOMENT"), JSON.stringify(await log(late)));
  await done(late);

  const off = await bar({ reply: [...filler(20), step({ phase: "tool_started", tool: "email_read" }), delta("Done. ")] });
  await off.evaluate(() => localStorage.setItem("jarvis.voice.oneMoment", "off"));
  await talk(off);
  await off.waitForTimeout(900);
  assert.ok(!(await log(off)).includes("play MOMENT"), JSON.stringify(await log(off)));
  await done(off);

  const none = await bar({ reply: [...filler(20), step({ phase: "tool_started", tool: "email_read" }), delta("Done. ")],
    momentFails: true });
  await talk(none);
  await none.waitForTimeout(900);
  assert.ok(!(await log(none)).includes("play MOMENT"));
  await done(none);

  const typed = await bar({ reply: [...filler(20), step({ phase: "tool_started", tool: "email_read" }), delta("Done. ")] });
  await typed.evaluate(() => window.__TAURI__.core.invoke("get_voice_flow"));
  await typed.fill("#prompt", "what is new");
  await typed.press("#prompt", "Enter");
  await typed.waitForTimeout(700);
  assert.ok(!(await log(typed)).includes("play MOMENT"));
  await done(typed);
});

await check("\"I heard you\": on letting go of the talk button, and when the PC heard \"hey Jarvis\" from you", async () => {
  const page = await bar({ reply: [delta("Hi. ")] });
  await talk(page);
  await page.waitForTimeout(200);
  assert.equal(await page.evaluate(() => window.__heardSounds), 1);
  assert.equal(await page.evaluate(() => window.__heardLength), CASES.heard_sound.samples);
  await done(page);

  const wake = await bar({ reply: [delta("Hi. ")] });
  await wake.locator("#voice-auto").click();
  await wake.waitForTimeout(100);
  await wake.evaluate(() => window.__emit("voice-heard", { isOwner: false, text: "", available: true, wakeHeard: false }));
  assert.equal(await wake.evaluate(() => window.__heardSounds), 0, "someone else, or not addressed: no sound");
  await wake.evaluate((h) => window.__emit("voice-heard", { ...h, source: "wake_word", wakeHeard: true }), K.HEARD_OWNER);
  await wake.waitForTimeout(100);
  assert.equal(await wake.evaluate(() => window.__heardSounds), 1);
  await done(wake);
});

await check("\"I heard you\" switched off: no sound on the talk button or for \"hey Jarvis\", and the question still goes", async () => {
  const page = await bar({ reply: [delta("Hi. ")] });
  await page.evaluate(() => localStorage.setItem("jarvis.voice.heardSound", "off"));
  await talk(page);
  await until(page, "play Hi.");
  assert.equal(await page.evaluate(() => window.__heardSounds), 0);
  await done(page);

  const wake = await bar({ reply: [delta("Hi. ")] });
  await wake.evaluate(() => localStorage.setItem("jarvis.voice.heardSound", "off"));
  await wake.locator("#voice-auto").click();
  await wake.waitForTimeout(100);
  await wake.evaluate((h) => window.__emit("voice-heard", { ...h, source: "wake_word", wakeHeard: true }), K.HEARD_OWNER);
  await wake.waitForTimeout(100);
  assert.equal(await wake.evaluate(() => window.__heardSounds), 0);
  // Switched back on (in Settings, another window): counts at once.
  await wake.evaluate(() => localStorage.setItem("jarvis.voice.heardSound", "on"));
  await wake.evaluate((h) => window.__emit("voice-heard", { ...h, source: "wake_word", wakeHeard: true }), K.HEARD_OWNER);
  await wake.waitForTimeout(100);
  assert.equal(await wake.evaluate(() => window.__heardSounds), 1);
  await done(wake);
});

await check("Settings: \"Say One moment\" is on by default, says what it does, and turning it off is saved", async () => {
  const page = await K.open(browser, base, "settings.html", {}, { width: 760, height: 1400 });
  const read = () => page.evaluate(() => ({
    checked: document.getElementById("voice-one-moment").checked,
    label: document.getElementById("voice-one-moment").closest("label").innerText,
    saved: localStorage.getItem("jarvis.voice.oneMoment"),
  }));
  const before = await read();
  assert.equal(before.checked, true);
  assert.ok(before.label.includes(F.MOMENT_NAME), before.label);
  assert.ok(before.label.includes(F.describeMoment(true)));
  await page.locator("#voice-one-moment").click();
  await page.waitForTimeout(100);
  const after = await read();
  await page.reload();
  await page.waitForTimeout(300);
  const reopened = await read();
  const errors = page.__errors;
  await page.close();
  assert.equal(after.checked, false);
  assert.equal(after.saved, "off");
  assert.ok(after.label.includes(F.describeMoment(false)));
  assert.equal(reopened.checked, false);
  assert.deepEqual(errors, []);
});

await check("Settings: \"Play a short sound\" is on by default, beside \"One moment\", and turning it off is saved", async () => {
  const page = await K.open(browser, base, "settings.html", {}, { width: 760, height: 1400 });
  const read = () => page.evaluate(() => {
    const box = document.getElementById("voice-heard-sound");
    const moment = document.getElementById("voice-one-moment").closest("label");
    return {
      checked: box.checked,
      label: box.closest("label").innerText,
      saved: localStorage.getItem("jarvis.voice.heardSound"),
      moment: localStorage.getItem("jarvis.voice.oneMoment"),
      besideMoment: moment.nextElementSibling === box.closest("label"),
    };
  });
  const before = await read();
  assert.equal(before.checked, true);
  assert.equal(before.besideMoment, true, "right under the One moment switch");
  assert.ok(before.label.includes(F.HEARD_NAME), before.label);
  assert.ok(before.label.includes(F.describeHeard(true)));
  await page.locator("#voice-heard-sound").click();
  await page.waitForTimeout(100);
  const after = await read();
  await page.reload();
  await page.waitForTimeout(300);
  const reopened = await read();
  const errors = page.__errors;
  await page.close();
  assert.equal(after.checked, false);
  assert.equal(after.saved, "off");
  assert.equal(after.moment, null, "\"One moment\" is left alone");
  assert.ok(after.label.includes(F.describeHeard(false)));
  assert.equal(reopened.checked, false);
  assert.deepEqual(errors, []);
});

/* ── Where the owner cut the answer off goes with the next question ──── */

await check("the cut-off sentence: once, with the next question only, and not two minutes later", async () => {
  const cut = F.createCutOff();
  assert.equal(cut.take(0), null);
  cut.cut("  Tomorrow looks mild.  ", 1000);
  assert.equal(cut.take(5000), "Tomorrow looks mild.");
  assert.equal(cut.take(6000), null, "once only");
  cut.cut("It clears by noon.", 1000);
  assert.equal(cut.take(1000 + F.CUT_OFF_KEEP_MS + 1), null);
  cut.cut("", 1000);
  cut.cut(null, 1000);
  assert.equal(cut.take(1001), null);
});

const lastChat = (page) => page.evaluate(() => {
  const chats = (window.__calls || []).filter(([cmd]) => cmd === "stream_chat");
  const args = chats.at(-1)?.[1];
  return args ? args.messages : null;
});

await check("stopped by the owner: the next question says where the answer was cut off", async () => {
  const bar2 = await bar({ reply: TWO });
  // A second answer, for the next question.
  await bar2.evaluate((next) => { window.__chatReplies.push(next); }, [delta("Sure. ")]);
  await talk(bar2);
  await until(bar2, "play One.");
  await skip(bar2, 3000);
  await onset(bar2, 5);
  await bar2.waitForTimeout(50);
  await verdict(bar2, { id: 5, stop: true, available: true, why: "owner_voice" });
  await bar2.waitForTimeout(400);
  const first = await lastChat(bar2);
  assert.ok(first && !first.some((m) => "interrupted" in m), "the first question carried nothing");
  // The answer finishes arriving on screen; then the owner asks again.
  await bar2.waitForTimeout(300);
  await talk(bar2);
  await bar2.waitForTimeout(500);
  const msgs = await lastChat(bar2);
  const newest = msgs.at(-1);
  assert.equal(newest.role, "user");
  assert.equal(newest.interrupted, "One.", JSON.stringify(msgs));
  assert.equal(msgs.filter((m) => "interrupted" in m).length, 1, "on the newest message only");
  // "Sure." is let play to its end this time (talking over it would cut it).
  await until(bar2, "end Sure.", 4000);
  await talk(bar2);
  await bar2.waitForTimeout(500);
  assert.ok(!(await lastChat(bar2)).some((m) => "interrupted" in m), "once only");
  await done(bar2);
});

await check("a PC that does not say it keeps the sentence on the PC is never sent it", async () => {
  const page = await bar({ reply: TWO, flow: { ...FLOW, cut_off: false } });
  await page.evaluate((next) => { window.__chatReplies.push(next); }, [delta("Sure. ")]);
  await talk(page);
  await until(page, "play One.");
  await talk(page); // the talk button over the reply cuts it off
  await page.waitForTimeout(500);
  assert.ok(!(await lastChat(page)).some((m) => "interrupted" in m));
  await done(page);
});

await check("an answer that played to its end: nothing is sent", async () => {
  const page = await bar({ reply: [delta("Hi. ")], playMs: 100 });
  await talk(page);
  await until(page, "end Hi.");
  await talk(page);
  await page.waitForTimeout(500);
  assert.ok(!(await lastChat(page)).some((m) => "interrupted" in m));
  await done(page);
});

await browser.close();
await close();
if (fails.length) {
  console.log(`\n${fails.length} failing: ${fails.join("; ")}`);
  process.exit(1);
}
console.log("\nThe voice flow holds");
