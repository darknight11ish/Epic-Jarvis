/**
 * Lip-sync plumbing on the desktop (face-voice.js, faces.html's LIP-SYNC,
 * voice.rs `face_voice`; docs/LIPSYNC.md).
 *
 * What must hold:
 * - the Jarvis bar sends each clip's mouth track once, before it sounds,
 *   then its playback clock - in order, with an id that only goes up - and
 *   says when the clip is over;
 * - a face frame follows that clock: the animal's mouth uniform is the
 *   track sampled where the audio is NOW, and the same loudness feeds the
 *   shell's voice envelope (so every face talks with the real voice);
 * - `speaking` with no real voice (a typed answer, Quiet mode, an answer
 *   kept on screen) keeps an animal's mouth SHUT;
 * - a paused clip freezes where it stopped and shuts the mouth; a message
 *   about an older clip is ignored;
 * - the microphone's level reaches the face, and goes back to 0 when it
 *   stops coming;
 * - the windows that hold a face pass all of this into it (an event reaches
 *   a window's page, never its frame).
 */
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { createRequire } from "node:module";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";
import * as K from "./uikit.mjs";

const HERE = dirname(fileURLToPath(import.meta.url));
const read = (p) => readFileSync(join(HERE, "..", p), "utf8");
const L = createRequire(import.meta.url)("../src/lipsync.js");

const { base, close } = await K.serve();
const browser = await K.launch();
const fails = [];
const check = async (name, fn) => {
  try { await fn(); console.log(`ok    ${name}`); }
  catch (e) { fails.push(name); console.log(`FAIL  ${name}\n      ${e.message}`); }
};

/* ── A clip with clear syllables ─────────────────────────────────────────── */

/** 16-bit mono PCM WAV, 24 kHz: silence, then 0.3 s bursts of a voiced
 *  tone with 0.3 s gaps - a mouth that must open in each burst and shut in
 *  each gap. 2.4 s long. */
function wav() {
  const rate = 24000, n = Math.round(rate * 2.4);
  const buf = Buffer.alloc(44 + n * 2);
  buf.write("RIFF", 0); buf.writeUInt32LE(36 + n * 2, 4); buf.write("WAVE", 8);
  buf.write("fmt ", 12); buf.writeUInt32LE(16, 16); buf.writeUInt16LE(1, 20); buf.writeUInt16LE(1, 22);
  buf.writeUInt32LE(rate, 24); buf.writeUInt32LE(rate * 2, 28); buf.writeUInt16LE(2, 32); buf.writeUInt16LE(16, 34);
  buf.write("data", 36); buf.writeUInt32LE(n * 2, 40);
  for (let i = 0; i < n; i += 1) {
    const t = i / rate;
    const on = t >= 0.3 && (Math.floor((t - 0.3) / 0.3) % 2 === 0) && t < 2.1;
    const v = on ? 0.55 * (Math.sin(2 * Math.PI * 180 * t) + 0.4 * Math.sin(2 * Math.PI * 900 * t)) : 0;
    buf.writeInt16LE(Math.max(-32768, Math.min(32767, Math.round(v * 32767))), 44 + i * 2);
  }
  return buf;
}
const WAV = wav();
const URI = "data:audio/wav;base64," + WAV.toString("base64");
const d = L.fromWav(new Uint8Array(WAV));
const PACKED = L.pack(L.analyse(d.samples, d.sampleRate));
const TRACK = L.unpack(PACKED);
const at = (t) => L.sample(TRACK, t);

/* ── A face frame the test drives the way a window does ──────────────────── */

const HOST = "voice-mouth-host.html";
/** A page on the app's own origin holding one display face, posted to from
 *  this page exactly as widget.js / floating.js / the HUD post to theirs. */
async function host(face = "redpanda") {
  const page = await browser.newPage({ viewport: { width: 300, height: 300 } });
  const errors = [];
  page.on("pageerror", (e) => errors.push(String(e)));
  await page.route(`${base}/${HOST}`, (route) => route.fulfill({
    status: 200, contentType: "text/html",
    body: `<!doctype html><meta charset="utf-8"><iframe id="f" style="width:240px;height:240px;border:0"
      src="faces.html?mode=display&feed=parent&face=${face}"></iframe>`,
  }));
  await page.goto(`${base}/${HOST}`);
  const frame = await faceFrame(page);
  return { page, frame, errors };
}
async function faceFrame(page) {
  const deadline = Date.now() + 8000;
  for (;;) {
    const frame = page.frames().find((f) => /\/faces\.html\?mode=display/.test(f.url()));
    if (frame) {
      const ready = await frame.evaluate(() => document.documentElement.dataset.hudFace).catch(() => null);
      if (ready === "ready") return frame;
    }
    if (Date.now() > deadline) throw new Error("the display face never became ready");
    await page.waitForTimeout(100);
  }
}
const post = (page, message) => page.evaluate((m) =>
  document.getElementById("f").contentWindow.postMessage(m, "/"), message);
const state = (page, s) => post(page, { type: "jarvis-hud-face", state: s });
const cue = (page, c) => post(page, { type: "jarvis-face-voice", ...c });
/** A clock read "now" on this PC's clock, as face-voice.js stamps it. */
const clock = (page, c) => page.evaluate((c) => {
  document.getElementById("f").contentWindow.postMessage({ type: "jarvis-face-voice", at: Date.now(), rate: 1, ...c }, "/");
}, c);
/** What the face drew last: its voice state, the animal's uMouth, the state. */
const drawn = (frame) => frame.evaluate(() => ({
  ...window.__faceVoice.now(), lastMouth: window.__faceVoice.lastMouth, lastState: window.__faceVoice.lastState,
}));
const near = (a, b, tol, what) => assert.ok(Math.abs(a - b) <= tol, `${what}: ${a} is not ${b} (±${tol})`);
/** Tell the face it is speaking and wait until the pose has melted fully
 *  into it, so the mouth is drawn at full size. The half-second melt starts
 *  on the first frame DRAWN in the new state, not when the message is
 *  posted - on a slow machine that frame comes late (CI once read the mouth
 *  at 0.88 of the track's 0.99, still melting, after a fixed 0.7 s wait). */
async function speakingSettled(page, frame) {
  await state(page, "speaking");
  for (const until = Date.now() + 3000; Date.now() < until;) {
    if ((await drawn(frame)).lastState === "speaking") break;
    await page.waitForTimeout(50);
  }
  await page.waitForTimeout(700);            // past the pose's half-second melt into speaking
}

/* ── The face ────────────────────────────────────────────────────────────── */

await check("the animal's mouth follows the track at the playback clock", async () => {
  const { page, frame, errors } = await host();
  await speakingSettled(page, frame);
  const id = 1790000000000;
  await cue(page, { id, n: 0, track: PACKED, t: 0, at: Date.now(), playing: false });
  let opens = [];
  for (const t of [0.42, 0.72, 1.02, 1.32]) {
    await clock(page, { id, n: Math.round(t * 100), t, playing: true });
    await page.waitForTimeout(60);
    const got = await drawn(frame);
    assert.equal(got.playing, true, "not playing");
    // It counts on from the clock, by the time since it was read.
    assert.ok(got.est >= t && got.est < t + 0.25, `at ${t}s it thinks the audio is at ${got.est}`);
    const want = at(got.est);
    near(got.lastMouth[0], want.open, 0.03, `open at ${got.est.toFixed(3)}s`);
    near(got.lastMouth[1], want.wide, 0.03, `wide at ${got.est.toFixed(3)}s`);
    near(got.lastMouth[2], want.round, 0.03, `round at ${got.est.toFixed(3)}s`);
    near(got.voiceRaw, want.level, 0.03, `the shell's voice level at ${got.est.toFixed(3)}s`);
    opens.push(got.lastMouth[0]);
  }
  await page.close();
  assert.deepEqual(errors, []);
  // In a burst the mouth is open; in a gap it is (nearly) shut.
  assert.ok(opens[0] > 0.3 && opens[2] > 0.3, `bursts: ${opens}`);
  assert.ok(opens[1] < opens[0] / 2 && opens[3] < opens[2] / 2, `gaps: ${opens}`);
});

await check("speaking with no real voice keeps an animal's mouth shut", async () => {
  // A typed answer, Quiet mode, an answer kept on screen: the backend still
  // says `speaking`, but nothing is playing.
  for (const face of ["redpanda", "pygmyowl", "seaotter", "monkey", "robot"]) {
    const { page, frame, errors } = await host(face);
    await state(page, "speaking");
    // The state takes effect on the face's next drawn frame: wait for it
    // (bounded) - on a busy machine that first frame can come late.
    for (const until = Date.now() + 3000; Date.now() < until;) {
      if ((await drawn(frame)).lastState === "speaking") break;
      await page.waitForTimeout(50);
    }
    let most = 0;
    for (let i = 0; i < 12; i += 1) {
      await page.waitForTimeout(80);
      const got = await drawn(frame);
      assert.equal(got.lastState, "speaking");
      most = Math.max(most, ...got.lastMouth);
    }
    await page.close();
    assert.deepEqual(errors, []);
    assert.equal(most, 0, `${face} moved its mouth with nothing playing`);
  }
});

await check("a paused clip freezes where it stopped and shuts the mouth; play carries on from there", async () => {
  const { page, frame } = await host();
  await speakingSettled(page, frame);
  const id = 1790000001000;
  await cue(page, { id, n: 0, track: PACKED, t: 0, at: Date.now(), playing: false });
  await clock(page, { id, n: 1, t: 0.45, playing: true });
  await page.waitForTimeout(60);
  assert.ok((await drawn(frame)).lastMouth[0] > 0.2, "the mouth was not open in a burst");
  await clock(page, { id, n: 2, t: 0.5, playing: false });
  await page.waitForTimeout(60);
  const a = await drawn(frame);
  await page.waitForTimeout(400);
  const b = await drawn(frame);
  assert.equal(b.playing, false);
  near(a.est, 0.5, 1e-6, "paused at");
  near(b.est, 0.5, 1e-6, "still paused at");
  assert.deepEqual(b.lastMouth, [0, 0, 0], "a paused clip left the mouth open");
  await clock(page, { id, n: 3, t: 0.5, playing: true });
  await page.waitForTimeout(150);
  const c = await drawn(frame);
  await page.close();
  assert.ok(c.est > 0.5 && c.est < 0.8, `resumed at ${c.est}`);
});

await check("messages about an older clip, or older messages about this one, are ignored", async () => {
  const { page, frame } = await host();
  const id = 1790000002000;
  await cue(page, { id, n: 0, track: PACKED, t: 0, at: Date.now(), playing: false });
  await clock(page, { id, n: 5, t: 1.0, playing: false });
  await clock(page, { id: id - 500, n: 9, t: 0.2, playing: true });     // an older clip
  await clock(page, { id, n: 4, t: 0.3, playing: true });               // overtaken on the way
  await page.waitForTimeout(80);
  const got = await drawn(frame);
  assert.equal(got.id, id);
  assert.equal(got.playing, false);
  near(got.est, 1.0, 1e-6, "position");
  // The end of the clip is the end: a clock after it changes nothing.
  await clock(page, { id, n: 6, t: 1.1, playing: false, end: true });
  await clock(page, { id, n: 7, t: 1.2, playing: true });
  await page.waitForTimeout(80);
  const after = await drawn(frame);
  await page.close();
  assert.equal(after.ended, true);
  assert.equal(after.mouth, null);
});

await check("while real voice plays, a resting face shows speaking - an approval stays an approval", async () => {
  const { page, frame } = await host("arc");
  await state(page, "idle");
  const id = 1790000003000;
  await cue(page, { id, n: 0, track: PACKED, t: 0, at: Date.now(), playing: false });
  await clock(page, { id, n: 1, t: 0.4, playing: true });
  await page.waitForTimeout(80);
  assert.equal((await drawn(frame)).lastState, "speaking");
  await state(page, "approval");
  await page.waitForTimeout(80);
  assert.equal((await drawn(frame)).lastState, "approval");
  await state(page, "idle");
  await clock(page, { id, n: 2, t: 0.6, playing: false, end: true });
  // Speaking is held for LIP_STATE_HOLD_S (2 s, faces.html) after the voice
  // stops, so a pause between sentences does not drop out of it; then idle.
  await page.waitForTimeout(2400);
  const got = await drawn(frame);
  await page.close();
  assert.equal(got.lastState, "idle", "still speaking after the voice ended");
});

await check("the microphone's level reaches the face, and drops when it stops coming", async () => {
  const { page, frame } = await host();
  await state(page, "listening");
  await post(page, { type: "jarvis-face-voice", mic: 0.8 });
  await page.waitForTimeout(40);
  near((await drawn(frame)).mic, 0.8, 1e-6, "mic level");
  await page.waitForTimeout(500);
  const got = await drawn(frame);
  await page.close();
  assert.equal(got.mic, 0, "the level stayed up after the microphone closed");
});

/* ── The windows pass it in ──────────────────────────────────────────────── */

await check("the floating face's window passes the voice and the microphone into its face", async () => {
  const page = await K.open(browser, base, "floating.html", {}, { width: 240, height: 240 });
  const frame = await faceFrame(page);
  const id = 1790000004000;
  await page.evaluate(([id, track]) => {
    window.__emit("face-voice", { id, n: 0, track, t: 0, at: Date.now(), playing: false, rate: 1 });
    window.__emit("face-voice", { id, n: 1, t: 0.4, at: Date.now(), playing: true, rate: 1 });
    window.__emit("voice-level", 0.6);
  }, [id, PACKED]);
  await page.waitForTimeout(80);
  const got = await drawn(frame);
  assert.equal(got.id, id);
  assert.equal(got.playing, true);
  near(got.mic, 0.6, 1e-6, "mic level");
  // A face that loads in the middle of a clip is handed the track again.
  await page.evaluate(() => { const f = document.getElementById("face-frame"); f.src = f.src; });
  // The relay hands the clip over on the frame's `load` event, a moment
  // AFTER the face marks itself ready, and the face only works out where
  // the audio is on its next drawn frame - so wait (bounded) for both,
  // rather than reading once at a fixed time: on a busy machine a single
  // read landed in one gap or the other (seen in CI, and 2 in 27 runs here).
  let again = null;
  const until = Date.now() + 5000;
  do {
    await page.waitForTimeout(100);
    again = await drawn(await faceFrame(page)).catch(() => null);
  } while ((!again || again.id !== id || !(again.est > 0.4)) && Date.now() < until);
  await page.close();
  assert.equal(again && again.id, id, "the reloaded face was not handed the clip");
  assert.ok(again.est > 0.4, `reloaded at ${again.est}`);
});

await check("every window that shows a face relays to it, and only the Jarvis bar sends", () => {
  assert.match(read("src/widget.js"), /relayFaceVoice\(dom\.faceFrame, listen\)/);
  assert.match(read("src/floating.js"), /relayFaceVoice\(frame, listen\)/);
  assert.match(read("src/jarvis_hud.html"), /import\("\.\/face-voice\.js"\)[\s\S]{0,120}relayFaceVoice\(frame,/);
  // The send is a Rust command in the quickbar's `voice` set only.
  const toml = read("src-tauri/permissions/surfaces.toml");
  const voiceSet = toml.slice(toml.indexOf('identifier = "voice"'), toml.indexOf('identifier = "hud-voice"'));
  assert.match(voiceSet, /"allow-face-voice"/);
  assert.equal((toml.match(/allow-face-voice/g) || []).length, 1, "another window may send lip-sync");
  // One limit for the track, both sides.
  const rs = read("src-tauri/src/voice.rs");
  const js = read("src/face-voice.js");
  assert.equal(Number(/FACE_VOICE_MAX_TRACK: usize = ([\d_]+)/.exec(rs)[1].replace(/_/g, "")),
    Number(/MAX_TRACK_CHARS = (\d+)/.exec(js)[1]));
  // The microphone's level goes to every window now, not only the quickbar.
  assert.doesNotMatch(rs, /emit_quickbar\([^)]*VOICE_LEVEL/);
  // What pack() writes is what Rust lets through.
  assert.match(PACKED, /^[A-Za-z0-9+/=:]+$/);
});

/* ── The sender ──────────────────────────────────────────────────────────── */

await check("a clip's track goes first, then its clock, in order, and its end", async () => {
  const page = await browser.newPage();
  await page.route(`${base}/blank.html`, (route) => route.fulfill({
    status: 200, contentType: "text/html", body: "<!doctype html><meta charset=utf-8>" }));
  await page.goto(`${base}/blank.html`);
  const cues = await page.evaluate(async (uri) => {
    const m = await import("./face-voice.js");
    const sent = [];
    const send = (c) => { sent.push(c); return Promise.resolve(); };
    const el = new EventTarget();
    Object.assign(el, { currentTime: 0, paused: true, ended: false, playbackRate: 1 });
    const stop = m.followClip(el, uri, { send, latency: 0.05 });
    el.paused = false; el.currentTime = 0.02; el.dispatchEvent(new Event("playing"));
    await new Promise((r) => setTimeout(r, 300));               // one timed clock
    el.currentTime = 0.8; el.paused = true; el.dispatchEvent(new Event("pause"));
    el.ended = true; el.dispatchEvent(new Event("ended"));
    stop();                                                     // again: harmless
    await new Promise((r) => setTimeout(r, 20));
    const el2 = Object.assign(new EventTarget(), { currentTime: 0, paused: true, ended: false, playbackRate: 1 });
    m.followClip(el2, uri, { send })();
    // An unreadable clip tells the faces nothing.
    const none = m.followClip(el2, "data:audio/wav;base64,AAAA", { send });
    none();
    await new Promise((r) => setTimeout(r, 20));
    return sent;
  }, URI);
  await page.close();
  const first = cues.filter((c) => c.id === cues[0].id);
  assert.equal(first[0].track, PACKED, "the track is not in the first message");
  assert.ok(first.slice(1).every((c) => c.track === undefined), "the track was sent twice");
  assert.deepEqual(first.map((c) => c.n), first.map((_, i) => i), "out of order");
  const playing = first.find((c) => c.playing);
  assert.ok(playing, "no playing clock");
  assert.equal(playing.t, 0, "the output delay was not taken off (0.02 - 0.05, floored at 0)");
  assert.ok(first.some((c) => c.playing && c.n > 1), "no clock while it played");
  const paused = first.find((c) => !c.playing && c.n > 1 && !c.end);
  assert.ok(paused && Math.abs(paused.t - 0.75) < 1e-9, `paused clock ${JSON.stringify(paused)}`);
  assert.equal(first.filter((c) => c.end).length, 1, "the end was not said exactly once");
  assert.equal(first[first.length - 1].end, true);
  const second = cues.filter((c) => c.id !== cues[0].id);
  assert.ok(second.length === 2 && second[0].id > cues[0].id, "the next clip's id did not go up");
});

/* ── Mouth shapes inside the WAV (the "jmth" chunk) ─────────────────────── */

const RES = join(HERE, "..", "..", "jarvis-client", "app", "src", "test", "resources");
const JMTH = readFileSync(join(RES, "lipsync-mouth", "kokoro-panda-lips-jmth.wav"));
const PLAIN = readFileSync(join(RES, "lipsync", "kokoro-panda-lips.wav"));
const uriOf = (b) => "data:audio/wav;base64," + b.toString("base64");

await check("a clip carrying the PC's mouth shapes sends them merged; a plain clip, the analysis as before", async () => {
  const page = await browser.newPage();
  await page.route(`${base}/blank.html`, (route) => route.fulfill({
    status: 200, contentType: "text/html", body: "<!doctype html><meta charset=utf-8>" }));
  await page.goto(`${base}/blank.html`);
  const got = await page.evaluate(async ([a, b]) => {
    const m = await import("./face-voice.js");
    return [m.trackFor(a), m.trackFor(b)];
  }, [uriOf(JMTH), uriOf(PLAIN)]);
  await page.close();
  const w = L.fromWav(new Uint8Array(JMTH)), p = L.fromWav(new Uint8Array(PLAIN));
  assert.ok(w.mouth, "the fixture carries a mouth");
  assert.equal(got[0], L.pack(L.merge(L.analyse(w.samples, w.sampleRate), w.mouth)), "not the merged track");
  assert.equal(got[1], L.pack(L.analyse(p.samples, p.sampleRate)), "a plain clip's track changed");
  assert.notEqual(got[0], got[1]);
});

await check("the browser plays a clip with the chunk exactly as without it (no extra sound)", async () => {
  const page = await browser.newPage();
  await page.route(`${base}/blank.html`, (route) => route.fulfill({
    status: 200, contentType: "text/html", body: "<!doctype html><meta charset=utf-8>" }));
  await page.goto(`${base}/blank.html`);
  const got = await page.evaluate(async ([a, b]) => {
    const decode = async (uri) => {
      const buf = await (await fetch(uri)).arrayBuffer();
      const ctx = new OfflineAudioContext(1, 1, 24000);
      const d = await ctx.decodeAudioData(buf);
      return { rate: d.sampleRate, len: d.length, data: Array.from(d.getChannelData(0)) };
    };
    const duration = (uri) => new Promise((resolve) => {
      const el = new Audio();
      el.preload = "metadata";
      el.onloadedmetadata = () => resolve(el.duration);
      el.onerror = () => resolve(`error ${el.error && el.error.code}`);
      el.src = uri;
    });
    return { with: await decode(a), without: await decode(b), dWith: await duration(a), dWithout: await duration(b) };
  }, [uriOf(JMTH), uriOf(PLAIN)]);
  await page.close();
  assert.equal(got.with.rate, got.without.rate);
  assert.equal(got.with.len, got.without.len, "the decoded length changed: the chunk was played as sound");
  assert.ok(got.with.data.every((x, i) => x === got.without.data[i]), "the decoded samples differ");
  assert.equal(got.dWith, got.dWithout, "the <audio> element's duration changed");
  assert.ok(typeof got.dWith === "number" && got.dWith > 1, `duration ${got.dWith}`);
});

await check("the Jarvis bar sends lip-sync for a spoken answer", async () => {
  const delta = (text) => JSON.stringify({ choices: [{ delta: { content: text } }] });
  const page = await K.open(browser, base, "index.html", {
    heard: K.HEARD_OWNER, chatReplies: [[delta("Hello there. ")]],
  });
  await K.slowSpeaker(page, 200);
  await page.evaluate((uri) => {
    const core = window.__TAURI__.core;
    const invoke = core.invoke;
    window.__faceCues = [];
    core.invoke = async (cmd, args) => {
      if (cmd === "face_voice") { window.__faceCues.push(args.cue); return null; }
      const out = await invoke(cmd, args);
      return cmd === "speak_reply" && typeof out === "string" ? uri + "#" + out.split("#")[1] : out;
    };
  }, URI);
  await page.hover("#mic");
  await page.mouse.down();
  await page.waitForTimeout(80);
  await page.mouse.up();
  await page.waitForTimeout(900);
  const cues = await page.evaluate(() => window.__faceCues);
  const log = await K.speechLog(page);
  await page.close();
  assert.deepEqual(log, ["speak Hello there.", "play Hello there.", "end Hello there."], JSON.stringify(log));
  assert.ok(cues.length >= 2, JSON.stringify(cues).slice(0, 200));
  assert.equal(cues[0].track, PACKED, "the answer's clip was not analysed and sent");
  assert.equal(cues[cues.length - 1].end, true, "its end was not sent");
});

await browser.close();
close();
if (fails.length) {
  console.log(`\n${fails.length} failed`);
  process.exit(1);
}
console.log("\nlip-sync plumbing holds");
