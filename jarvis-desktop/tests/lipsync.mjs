/**
 * Lip-sync core (src/lipsync.js): the mouth track every face reads while
 * Jarvis speaks. Needs no browser.
 *
 * It checks the analysis against Jarvis's real voice - the Kokoro test clips
 * the phone's LipSyncTest also reads (jarvis-client/app/src/test/resources/
 * lipsync/, made as docs/LIPSYNC.md says) - so "the mouth closes in the
 * pauses" and "oo looks round, ee looks spread" are measured on the voice
 * the owner hears, not on a synthetic tone. Then the plumbing: pack/unpack
 * between windows, WAV decoding (mono, stereo, odd chunks), sample()'s lead
 * and edges, the speed of a 10 s clip, and that the phone's golden fixture
 * is fresh.
 */
import assert from "node:assert/strict";
import { readFileSync, readdirSync, existsSync } from "node:fs";
import { execFileSync } from "node:child_process";
import { createRequire } from "node:module";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";
import vm from "node:vm";

const HERE = dirname(fileURLToPath(import.meta.url));
const ROOT = join(HERE, "..");
const REPO = join(ROOT, "..");
const require = createRequire(import.meta.url);
const L = require(join(ROOT, "src", "lipsync.js"));
const CLIPS = join(REPO, "jarvis-client", "app", "src", "test", "resources", "lipsync");

const fails = [];
const check = (name, fn) => {
  try { fn(); console.log(`ok    ${name}`); }
  catch (e) { fails.push(name); console.log(`FAIL  ${name}\n      ${e.message}`); }
};

const load = (name) => {
  const w = L.fromWav(readFileSync(join(CLIPS, name)));
  return { ...w, track: L.analyse(w.samples, w.sampleRate) };
};
const mean = (a) => a.reduce((s, x) => s + x, 0) / Math.max(1, a.length);

// Frames whose own 10 ms of audio is truly quiet (peak under -50 dBFS), in
// runs of 120 ms or more, minus 40 ms at each end: silence judged from the
// samples themselves, not from the analysis under test.
function silentFrames({ samples, sampleRate, track }) {
  const hop = sampleRate / L.FPS, quiet = [];
  for (let i = 0; i < track.n; i++) {
    let pk = 0;
    for (let k = Math.floor(i * hop); k < Math.min(samples.length, Math.floor((i + 1) * hop)); k++) {
      pk = Math.max(pk, Math.abs(samples[k]));
    }
    quiet.push(pk < 0.003);
  }
  const out = [];
  for (let i = 0; i < track.n;) {
    if (!quiet[i]) { i++; continue; }
    let j = i;
    while (j < track.n && quiet[j]) j++;
    if (j - i >= 12) for (let k = i + 4; k < j - 4; k++) out.push(k);
    i = j;
  }
  return out;
}
// Closures: the mouth drops below 0.12 between two openings above 0.25.
function closures(open) {
  let count = 0, low = 1, armed = false;
  for (const o of open) {
    if (o > 0.25) { if (armed && low < 0.12) count++; armed = true; low = 1; }
    else if (armed) low = Math.min(low, o);
  }
  return count;
}
// Mean wide / round over the louder half of the voiced frames.
function lipShape(track) {
  const ks = [];
  for (let i = 0; i < track.n; i++) if (track.open[i] > 0.3) ks.push(i);
  return { wide: mean(ks.map((i) => track.wide[i])), round: mean(ks.map((i) => track.round[i])) };
}

/* ── The shape of the module ──────────────────────────────────────────────── */

check("a classic script: no import/export, sets globalThis.JarvisLipSync", () => {
  const src = readFileSync(join(ROOT, "src", "lipsync.js"), "utf8");
  assert.ok(!/^\s*(import|export)\s/m.test(src), "an import/export statement would break <script src>");
  const ctx = {};
  vm.runInNewContext(src, ctx);
  assert.equal(typeof ctx.JarvisLipSync?.analyse, "function");
  for (const k of ["analyse", "sample", "fromWav", "pack", "unpack", "mouthFrom", "merge"]) assert.equal(typeof L[k], "function", k);
  assert.equal(L.FPS, 100);
  assert.ok(L.LEAD_S > 0 && L.LEAD_S <= 0.1, `LEAD_S ${L.LEAD_S}`);
});

check("the Kotlin copy has the same FPS and LEAD_S", () => {
  const kt = readFileSync(join(REPO, "jarvis-client", "app", "src", "main", "java", "com", "jarvis", "client",
    "audio", "LipSync.kt"), "utf8");
  assert.match(kt, new RegExp(`const val FPS = ${L.FPS}\\b`));
  assert.match(kt, new RegExp(`const val LEAD_S = ${L.LEAD_S}f\\b`));
  assert.match(kt, new RegExp(`const val ONSET_S = ${L.ONSET_S}f\\b`));
});

/* ── Measured on Jarvis's own voice ───────────────────────────────────────── */

const names = existsSync(CLIPS) ? readdirSync(CLIPS).filter((f) => f.endsWith(".wav")).sort() : [];
check("the Kokoro test clips are there", () => assert.ok(names.length >= 5, `found ${names.length}`));
const clips = Object.fromEntries(names.map((n) => [n.replace(/^kokoro-|\.wav$/g, ""), load(n)]));

check("every track is in range, 100 frames a second, the clip's length", () => {
  for (const [name, c] of Object.entries(clips)) {
    assert.equal(c.track.fps, 100);
    assert.equal(c.track.n, Math.ceil(c.samples.length * 100 / c.sampleRate), name);
    for (const ch of ["level", "open", "wide", "round"]) {
      for (const v of c.track[ch]) assert.ok(v >= 0 && v <= 1 && Number.isFinite(v), `${name} ${ch} ${v}`);
    }
  }
});

check("the mouth is shut in the silences (every clip, every voice)", () => {
  let frames = 0;
  for (const [name, c] of Object.entries(clips)) {
    const sil = silentFrames(c);
    frames += sil.length;
    for (const i of sil) assert.ok(c.track.open[i] < 0.01, `${name}: open ${c.track.open[i]} at silent frame ${i}`);
  }
  assert.ok(frames >= 30, `only ${frames} silent frames to judge by`);
});

check("\"Okay. Let me check. Done.\" closes between the sentences and opens for each", () => {
  const c = clips["default-pauses"], sil = silentFrames(c);
  assert.ok(sil.length >= 20, `silent frames ${sil.length}`);
  assert.ok(Math.max(...c.track.open) > 0.6, "opens properly when speaking");
  assert.ok(closures(c.track.open) >= 2, `closures ${closures(c.track.open)}`);
});

check("\"Maybe Bob made a map.\" closes the lips for the m / b / p, in every voice", () => {
  for (const name of Object.keys(clips).filter((n) => n.endsWith("-lips"))) {
    const n = closures(clips[name].track.open);
    assert.ok(n >= 3, `${name}: ${n} closures between openings (m-ay-B-e B-o-B m-ade a m-ap)`);
  }
});

check("oo looks round and ee looks spread", () => {
  const r = lipShape(clips["default-round"].track), w = lipShape(clips["default-wide"].track);
  // "Who knew the moon would glow so blue?" / "Please see these three sheep."
  assert.ok(r.round > r.wide, `round sentence: round ${r.round.toFixed(2)} vs wide ${r.wide.toFixed(2)}`);
  assert.ok(w.wide > w.round + 0.2, `wide sentence: wide ${w.wide.toFixed(2)} vs round ${w.round.toFixed(2)}`);
  assert.ok(w.wide > r.wide + 0.15, "the spread sentence is wider than the rounded one");
  assert.ok(r.round > w.round + 0.1, "the rounded sentence is rounder than the spread one");
  if (clips["otter-wide"]) {
    const o = lipShape(clips["otter-wide"].track);
    assert.ok(o.wide > o.round + 0.2, `otter (pitched +3 semitones): wide ${o.wide.toFixed(2)} vs round ${o.round.toFixed(2)}`);
  }
});

// Played slower or faster by the same rule as jarvis_speech.pitch_up (the
// animals' pitch setting): every frequency x 2^(semitones/12).
function pitched(x, semitones) {
  const f = 2 ** (semitones / 12), n = Math.floor(x.length / f), y = new Float32Array(n);
  for (let i = 0; i < n; i++) {
    const s = i * f, a = Math.floor(s), b = Math.min(a + 1, x.length - 1);
    y[i] = x[a] + (x[b] - x[a]) * (s - a);
  }
  return y;
}

check("a deeper or higher voice still looks spread on ee and round on oo (the lip bands follow the pitch)", () => {
  // kokoro-default-wide-deep: "Please see these three sheep." 3 semitones
  // deeper. Before the bands followed the pitch it read round 0.26, wide 0.11.
  const d = lipShape(clips["default-wide-deep"].track);
  assert.ok(d.wide > d.round + 0.05, `3 semitones deeper: wide ${d.wide.toFixed(2)} vs round ${d.round.toFixed(2)}`);
  // The default voice from 3 deeper to 2 higher (at +4 the "oo" sentence
  // was already a tie, 0.19 round vs 0.18 wide, before and after).
  for (const semis of [-3, -1.5, 2]) {
    for (const [name, want] of [["default-wide", "wide"], ["default-round", "round"]]) {
      const c = clips[name], s = lipShape(L.analyse(pitched(c.samples, semis), c.sampleRate));
      const other = want === "wide" ? "round" : "wide";
      assert.ok(s[want] > s[other] + 0.05, `${name} ${semis > 0 ? "+" : ""}${semis} semitones: ${want} ${s[want].toFixed(2)} vs ${other} ${s[other].toFixed(2)}`);
    }
  }
  // The otter's voice (Kokoro speaker 4) set to 3 semitones deeper, where
  // its clip says +3: 6 down. It read round 0.43, wide 0.06; now spread,
  // though only just (the bands move at most 3/8 of an octave).
  const o = clips["otter-wide"], os = lipShape(L.analyse(pitched(o.samples, -6), o.sampleRate));
  assert.ok(os.wide > os.round, `otter at -3 semitones: wide ${os.wide.toFixed(2)} vs round ${os.round.toFixed(2)}`);
});

check("a steady noise floor does not keep the mouth moving in the pauses", () => {
  // kokoro-default-pauses-noisy: "Okay. Let me check. Done." with white
  // noise 20 dB under the speech, as a voice cloned from a recording made in
  // a noisy room carries. The pauses are judged from the clean clip; before
  // the gate followed the noise floor the mouth opened to 0.3 in them and
  // the loudness sat at 0.24.
  const clean = clips["default-pauses"], noisy = clips["default-pauses-noisy"], sil = silentFrames(clean);
  assert.ok(sil.length >= 20, `silent frames ${sil.length}`);
  const open = Math.max(...sil.map((i) => noisy.track.open[i])), level = mean(sil.map((i) => noisy.track.level[i]));
  assert.ok(open < 0.02, `open ${open.toFixed(3)} in a pause`);
  assert.ok(level < 0.1, `loudness ${level.toFixed(3)} in the pauses`);
  const r = corr(noisy.track.open, clean.track.open);
  assert.ok(r > 0.95, `the opening correlates ${r.toFixed(3)} with the clean clip's`);
  assert.ok(closures(noisy.track.open) >= 2, `closures ${closures(noisy.track.open)}`);
});

check("wide and round are never both high", () => {
  for (const [name, c] of Object.entries(clips)) {
    for (let i = 0; i < c.track.n; i++) {
      assert.ok(Math.min(c.track.wide[i], c.track.round[i]) < 0.3, `${name} frame ${i}`);
    }
  }
});

/* ── Other rates, short clips, a clip cut off mid-word, the sound roughed up ─ */
// kokoro-default-hi (24 kHz, 0.66 s), -panda-endcut-16k (cut off inside
// "ready"), -default-call-22k (22.05 kHz: a mouth frame is 220.5 samples),
// -owl-hear-44k (44.1 kHz: the 1024-sample window), -otter-wait-8k (8 kHz,
// nothing above 4 kHz), -otter-sheep ("sh" x 4). Kokoro's real voice,
// resampled with a windowed sinc; the phone checks every frame of them too.

check("the other sample rates and a very short reply open for speech, in every voice", () => {
  for (const name of ["default-hi", "panda-endcut-16k", "default-call-22k", "owl-hear-44k", "otter-wait-8k", "otter-sheep"]) {
    const c = clips[name];
    assert.ok(c, `${name} is missing`);
    assert.ok(Math.max(...c.track.open) > 0.5, `${name}: opens to ${Math.max(...c.track.open).toFixed(2)}`);
    assert.ok(Math.max(...c.track.level) > 0.9, `${name}: level`);
  }
  assert.equal(clips["owl-hear-44k"].sampleRate, 44100);
  assert.equal(clips["otter-wait-8k"].sampleRate, 8000);
  assert.ok(closures(clips["otter-wait-8k"].track.open) >= 2, "\"Wait... wait... okay, now.\" closes between the words at 8 kHz");
});

check("a clip that ends mid-word does not snap the mouth shut (the end fade)", () => {
  const t = clips["panda-endcut-16k"].track;
  assert.ok(t.open[t.n - 1] > 0.3, `the cut is inside a vowel: open ${t.open[t.n - 1]}`);
  const last = (t.n - 1) / t.fps - L.LEAD_S;
  let prev = null, step = 0;
  for (let s = last - 0.3; s <= last + 0.1; s += 1 / 60) { // a 60 Hz screen
    const o = L.sample(t, s), v = [o.open, o.wide, o.round];
    if (prev) step = Math.max(step, ...v.map((x, i) => Math.abs(x - prev[i])));
    prev = v;
  }
  assert.ok(step < 0.3, `biggest step between two screen frames at the end: ${step.toFixed(2)}`);
  assert.deepEqual(prev, [0, 0, 0], "shut after the end");
});

// A deterministic noise source, so the test gives the same numbers every run.
function lcg(seed) {
  return () => { seed = (seed * 1103515245 + 12345) % 2147483648; return seed / 2147483648; };
}
function corr(a, b) {
  const n = a.length, ma = mean(a), mb = mean(b);
  let ab = 0, aa = 0, bb = 0;
  for (let i = 0; i < n; i++) { const x = a[i] - ma, y = b[i] - mb; ab += x * y; aa += x * x; bb += y * y; }
  return ab / Math.sqrt(aa * bb + 1e-30);
}

check("the mouth barely changes when the sound is quieter, louder, clipped, noisy, hummy or resampled", () => {
  const c = clips["default-pauses"], x = c.samples, sr = c.sampleRate, want = c.track.open;
  const q16 = (f) => Float32Array.from(x, (v, i) => Math.max(-32768, Math.min(32767, Math.round(f(v, i) * 32768))) / 32768);
  const rnd = lcg(12345), gauss = () => Math.sqrt(-2 * Math.log(rnd() || 1e-9)) * Math.cos(2 * Math.PI * rnd());
  let p = 0, k = 0;
  for (const v of x) if (Math.abs(v) > 0.003) { p += v * v; k++; }
  const noise30 = Math.sqrt(p / k / 1000); // 30 dB below the speech
  const variants = {
    "40 dB quieter": q16((v) => v * 0.01),
    "12 dB louder, clipped": q16((v) => Math.max(-1, Math.min(1, v * 4))),
    "hiss 30 dB below the speech": q16((v) => v + noise30 * gauss()),
    "60 Hz hum at -30 dBFS": q16((v, i) => v + 0.0316 * Math.sin(2 * Math.PI * 60 * i / sr)),
    "a chord at -30 dBFS": q16((v, i) => v + 0.0316 * (Math.sin(2 * Math.PI * 220 * i / sr) + Math.sin(2 * Math.PI * 277 * i / sr) +
      Math.sin(2 * Math.PI * 330 * i / sr)) / 3),
  };
  for (const [name, y] of Object.entries(variants)) {
    const t = L.analyse(y, sr), r = corr(t.open, want);
    assert.equal(t.n, c.track.n, name);
    assert.ok(r > 0.95, `${name}: the mouth's opening correlates ${r.toFixed(3)} with the clean clip's`);
  }
  // The same sound at other rates (linear interpolation): the same mouth.
  for (const rate of [16000, 44100, 48000]) {
    const n = Math.floor(x.length * rate / sr), y = new Float32Array(n);
    for (let i = 0; i < n; i++) {
      const s = i * sr / rate, a = Math.floor(s), b = Math.min(a + 1, x.length - 1);
      y[i] = x[a] + (x[b] - x[a]) * (s - a);
    }
    const t = L.analyse(y, rate), m = Math.min(t.n, want.length);
    const r = corr(t.open.subarray(0, m), want.subarray(0, m));
    assert.ok(r > 0.95, `at ${rate} Hz the opening correlates ${r.toFixed(3)} with 24 kHz`);
  }
});

/* ── sample(): the playback clock plus the lead ──────────────────────────── */

check("sample() reads LEAD_S ahead, interpolates, and is all zeros outside", () => {
  const n = 40, ramp = Float32Array.from({ length: n }, (_, i) => i / (n - 1));
  const t = { fps: 100, n, level: ramp, open: ramp, wide: new Float32Array(n), round: new Float32Array(n) };
  assert.equal(L.sample(null, 0.1), null);
  const at0 = L.sample(t, 0);
  assert.ok(Math.abs(at0.level - (L.LEAD_S * 100) / (n - 1)) < 1e-6, "t=0 reads frame LEAD_S*FPS");
  const mid = L.sample(t, 0.075 - L.LEAD_S);
  assert.ok(Math.abs(mid.level - 7.5 / (n - 1)) < 1e-6, "halfway between frames 7 and 8");
  // The mouth (not the level) fades in over the clip's first ONSET_S.
  assert.equal(L.ONSET_S, 0.05);
  assert.equal(at0.open, 0, "the mouth starts shut at t = 0");
  assert.ok(Math.abs(mid.open - 0.5 * 7.5 / (n - 1)) < 1e-6, "half faded in at 25 ms");
  const full = L.sample(t, 0.1);
  assert.ok(Math.abs(full.open - full.level) < 1e-6, "fully in from ONSET_S on");
  // ...and fades out over the track's last ONSET_S (the level does not): a
  // clip whose sound runs to its end must not snap shut in one frame.
  const lastT = (n - 1) / 100 - L.LEAD_S;
  const tail = L.sample(t, lastT - 0.025);
  assert.ok(Math.abs(tail.level - (n - 3.5) / (n - 1)) < 1e-6, "the level is not faded at the end");
  assert.ok(Math.abs(tail.open - 0.5 * tail.level) < 1e-6, `half faded out 25 ms before the end: ${tail.open}`);
  assert.ok(L.sample(t, lastT - 1e-4).open < 0.01, "shut at the last frame");
  assert.ok(Math.abs(L.sample(t, lastT - 0.06).open - L.sample(t, lastT - 0.06).level) < 1e-6, "not faded before the last ONSET_S");
  const zero = { level: 0, open: 0, wide: 0, round: 0 };
  assert.deepEqual({ ...L.sample(t, -L.LEAD_S - 0.001) }, zero, "before the start");
  assert.deepEqual({ ...L.sample(t, (n - 1) / 100 - L.LEAD_S + 0.001) }, zero, "after the end");
  const out = { level: 9, open: 9, wide: 9, round: 9 };
  assert.equal(L.sample(t, 0.02, out), out, "fills the object it is given");
  assert.deepEqual({ ...L.sample(t, 1e9, out) }, zero);
  const empty = L.analyse(new Float32Array(0), 24000);
  assert.equal(empty.n, 0);
  assert.deepEqual({ ...L.sample(empty, 0) }, zero);
  assert.equal(L.analyse(new Float32Array(1000), 0).n, 0, "a bad sample rate gives an empty track");
});

/* ── Between windows: pack / unpack ───────────────────────────────────────── */

check("pack/unpack round-trips a real track within one step of 1/255", () => {
  const tr = clips["default-lips"].track, s = L.pack(tr), back = L.unpack(s);
  assert.equal(typeof s, "string");
  assert.ok(/^[0-9]+:[A-Za-z0-9+/=]*$/.test(s), "plain base64 after the fps");
  assert.equal(back.fps, tr.fps);
  assert.equal(back.n, tr.n);
  for (const ch of ["level", "open", "wide", "round"]) {
    for (let i = 0; i < tr.n; i++) assert.ok(Math.abs(back[ch][i] - tr[ch][i]) <= 0.5 / 255 + 1e-6, `${ch}[${i}]`);
  }
  assert.ok(s.length < tr.n * 6, `compact: ${s.length} characters for ${tr.n} frames`);
  // Every length mod 3 of the byte stream, and the empty track.
  for (const n of [0, 1, 2, 3, 7]) {
    const t = { fps: 100, n, level: new Float32Array(n).fill(1), open: new Float32Array(n).fill(0.5),
      wide: new Float32Array(n), round: new Float32Array(n).fill(0.25) };
    const u = L.unpack(L.pack(t));
    assert.equal(u.n, n);
    for (let i = 0; i < n; i++) {
      assert.equal(u.level[i], 1); assert.ok(Math.abs(u.open[i] - 0.5) < 0.003); assert.ok(Math.abs(u.round[i] - 0.25) < 0.003);
    }
  }
});

/* ── fromWav ──────────────────────────────────────────────────────────────── */

function wav({ rate = 24000, channels = 1, bits = 16, frames, extra = null }) {
  const data = new Int16Array(frames.length * channels);
  frames.forEach((f, i) => { for (let c = 0; c < channels; c++) data[i * channels + c] = Array.isArray(f) ? f[c] : f; });
  const dataBytes = new Uint8Array(data.buffer);
  const chunks = [];
  const chunk = (id, body) => {
    const h = new Uint8Array(8 + body.length + (body.length & 1));
    h.set([...id].map((ch) => ch.charCodeAt(0)), 0);
    new DataView(h.buffer).setUint32(4, body.length, true);
    h.set(body, 8);
    chunks.push(h);
  };
  const fmt = new Uint8Array(16), dv = new DataView(fmt.buffer);
  dv.setUint16(0, 1, true); dv.setUint16(2, channels, true); dv.setUint32(4, rate, true);
  dv.setUint32(8, rate * channels * bits / 8, true); dv.setUint16(12, channels * bits / 8, true); dv.setUint16(14, bits, true);
  chunk("fmt ", fmt);
  if (extra) chunk("LIST", extra);
  chunk("data", dataBytes);
  chunk("LIST", new Uint8Array([1, 2, 3])); // metadata after data must not be read as sound
  const body = chunks.reduce((s, c) => s + c.length, 4);
  const out = new Uint8Array(8 + body);
  out.set([82, 73, 70, 70], 0); new DataView(out.buffer).setUint32(4, body, true); out.set([87, 65, 86, 69], 8);
  let p = 12;
  for (const c of chunks) { out.set(c, p); p += c.length; }
  return out;
}

check("fromWav reads mono and stereo (averaged) 16-bit, whatever chunks surround the data", () => {
  const m = L.fromWav(wav({ rate: 16000, frames: [0, 16384, -32768, 32767] }));
  assert.equal(m.sampleRate, 16000);
  assert.deepEqual(Array.from(m.samples), [0, 0.5, -1, 32767 / 32768]);
  const s = L.fromWav(wav({ rate: 44100, channels: 2, frames: [[16384, 0], [-16384, -16384], [100, -100]],
    extra: new Uint8Array(5) }));
  assert.equal(s.sampleRate, 44100);
  assert.deepEqual(Array.from(s.samples), [0.25, -0.5, 0]);
  const fromBuf = L.fromWav(wav({ frames: [8192] }).buffer);
  assert.deepEqual(Array.from(fromBuf.samples), [0.25], "an ArrayBuffer works too");
  const eight = L.fromWav(wav({ bits: 8, frames: [1, 2] }));
  assert.equal(eight.samples.length, 0, "not 16-bit: no samples rather than noise");
  assert.equal(L.fromWav(new Uint8Array(10)).samples.length, 0, "not a WAV");
});

check("fromWav never throws, and refuses what it cannot read (cut short, short fmt, nonsense rate)", () => {
  const good = wav({ frames: Array.from({ length: 480 }, (_, i) => (i * 97) % 2000 - 1000) });
  // Cut short at every length through the header and into the data: no
  // exception (a file cut inside `fmt ` used to throw a RangeError).
  for (let cut = 0; cut <= 60; cut++) {
    const w = L.fromWav(good.subarray(0, cut));
    assert.ok(w.samples instanceof Float32Array, `cut to ${cut} bytes`);
  }
  // A fmt chunk too short to hold its fields is not read past its end.
  const shortFmt = good.slice();
  new DataView(shortFmt.buffer).setUint32(16, 4, true);
  assert.equal(L.fromWav(shortFmt).samples.length, 0, "fmt of 4 bytes");
  // Rates the phone refuses too (Wav.rateOf: 4000..192000): 1 Hz would ask
  // for 100 mouth frames per sample.
  for (const rate of [0, 1, 3999, 192001, 4e9]) {
    assert.equal(L.fromWav(wav({ rate, frames: [1, 2, 3] })).samples.length, 0, `rate ${rate}`);
  }
  for (const rate of [4000, 8000, 11025, 16000, 22050, 44100, 48000, 96000, 192000]) {
    assert.equal(L.fromWav(wav({ rate, frames: [1, 2, 3] })).samples.length, 3, `rate ${rate}`);
  }
});

check("a sample that is not a number counts as silence - never a NaN mouth", () => {
  const rate = 24000, clean = new Float32Array(rate);
  for (let i = 6000; i < 18000; i++) clean[i] = 0.4 * Math.sin(2 * Math.PI * 200 * i / rate);
  const want = L.analyse(clean, rate);
  for (const bad of [NaN, Infinity, -Infinity]) {
    const dirty = clean.slice(); dirty[3000] = bad;
    const got = L.analyse(dirty, rate);
    for (const ch of ["level", "open", "wide", "round"]) assert.deepEqual(Array.from(got[ch]), Array.from(want[ch]), `${bad} ${ch}`);
    dirty[12000] = bad;
    const mid = L.analyse(Array.from(dirty), rate); // a plain array too
    for (const ch of ["level", "open", "wide", "round"]) for (const v of mid[ch]) assert.ok(v >= 0 && v <= 1, `${bad} in the sound: ${ch} ${v}`);
  }
});

/* ── Mouth shapes inside the WAV: the "jmth" chunk ──────────────────────── */

const RES = join(REPO, "jarvis-client", "app", "src", "test", "resources");
const golden = JSON.parse(readFileSync(join(RES, "lipsync-golden.json"), "utf8"));

check("a clip with a jmth chunk: the same sound, plus the PC's mouth shapes", () => {
  const src = L.fromWav(readFileSync(join(CLIPS, golden.mouth.source)));
  const fx = L.fromWav(readFileSync(join(RES, "lipsync-mouth", golden.mouth.file)));
  assert.deepEqual(Array.from(fx.samples), Array.from(src.samples), "the chunk was read as sound");
  assert.equal(fx.sampleRate, src.sampleRate);
  assert.equal(src.mouth, undefined, "a clip without the chunk has no mouth - exactly as before");
  assert.ok(fx.mouth && fx.mouth.fps === 100, "no mouth read from the chunk");
  const audio = L.analyse(fx.samples, fx.sampleRate), m = L.merge(audio, fx.mouth);
  assert.equal(fx.mouth.n, audio.n - 2);
  assert.equal(m.n, audio.n);
  assert.equal(m.level, audio.level, "the level is the clip's own");
  for (let i = 0; i < m.n; i++) {
    const want = i < fx.mouth.n ? [fx.mouth.open[i], fx.mouth.wide[i], fx.mouth.round[i]] : [0, 0, 0];
    assert.deepEqual([m.open[i], m.wide[i], m.round[i]], want, `frame ${i}`);
  }
  // pack() gives back the very string the chunk carried.
  const text = readFileSync(join(RES, "lipsync-mouth", golden.mouth.file)).toString("latin1");
  const packed = text.slice(text.indexOf("v1;src=fixture;") + 15).replace(/\0+$/, "");
  assert.equal(L.pack(fx.mouth), packed);
});

check("every good and broken jmth variant is read as meant (gen_lipsync.py's list)", () => {
  const want = { "merged": 0, "kept apart": 0, "ignored": 0 };
  for (const c of golden.mouth.cases) {
    want[c.want]++;
    const seen = c.merged ? "merged" : c.mouth ? "kept apart" : "ignored";
    assert.equal(seen, c.want, c.name);
    assert.ok(c.sameSound, `${c.name}: the sound changed`);
  }
  assert.ok(want.merged >= 5 && want["kept apart"] >= 2 && want.ignored >= 10, JSON.stringify(want));
});

check("fromWav: a broken or misplaced jmth chunk changes nothing", () => {
  const frames = [0, 16384, -32768, 32767];
  const plain = L.fromWav(wav({ frames }));
  const chunk = (payload, size = payload.length) => {
    const b = new Uint8Array(8 + payload.length + (size & 1));
    b.set([106, 109, 116, 104]); new DataView(b.buffer).setUint32(4, size, true);
    for (let i = 0; i < payload.length; i++) b[8 + i] = payload.charCodeAt(i);
    return b;
  };
  const withChunk = (c, before = false) => {
    const base = wav({ frames }), at = before ? 36 : base.length;
    const out = new Uint8Array(base.length + c.length);
    out.set(base.subarray(0, at)); out.set(c, at); out.set(base.subarray(at), at + c.length);
    new DataView(out.buffer).setUint32(4, out.length - 8, true);
    return out;
  };
  const good = "v1;src=kokoro;100:/wCAAQ==";
  const ok = L.fromWav(withChunk(chunk(good)));
  assert.deepEqual(Array.from(ok.samples), Array.from(plain.samples));
  assert.equal(ok.mouth.n, 1);
  assert.deepEqual([ok.mouth.level[0], ok.mouth.open[0]], [1, 0]);
  assert.ok(Math.abs(ok.mouth.wide[0] - 128 / 255) < 1e-6 && Math.abs(ok.mouth.round[0] - 1 / 255) < 1e-6);
  const broken = {
    "version 2": withChunk(chunk("v2;src=kokoro;100:/wCAAQ==")),
    "bad base64": withChunk(chunk("v1;src=kokoro;100:/w*AAQ==")),
    "not whole frames": withChunk(chunk("v1;src=kokoro;100:/wCA")),
    "another frame rate": withChunk(chunk("v1;src=kokoro;50:/wCAAQ==")),
    "before data": withChunk(chunk(good), true),
    "declared past the end": withChunk(chunk(good, good.length + 9)),
    "cut short": withChunk(chunk(good)).subarray(0, 60 + good.length),
    "odd size, one byte short": withChunk(chunk(good, good.length - 1)),
  };
  for (const [name, bytes] of Object.entries(broken)) {
    const w = L.fromWav(bytes);
    assert.equal(w.mouth, undefined, name);
    assert.deepEqual(Array.from(w.samples), Array.from(plain.samples), name);
    assert.equal(w.sampleRate, plain.sampleRate, name);
  }
});

check("mouthFrom / merge: the same rules as the phone's LipSync.mouthFrom / unpack / merge", () => {
  for (const bad of ["", "v1;", "v1;100:", "v1;50:/wCAAQ==", "v1;100/wCAAQ==", "v1;100:/wCAAQ=", "v1;100:/wCAAQ",
    "v1;100:/wC*AQ==", "v1;100:/w==AQ==", "v1;100:/wCA", "v1;abc:/wCAAQ==", "v1; 100:/wCAAQ==", "v1;10000:/wCAAQ==",
    "v1;src=kokoro", "v1;src=kokoro;;100:/wCAAQ==", "V1;100:/wCAAQ==", null, 7]) {
    assert.equal(L.mouthFrom(bad), null, JSON.stringify(bad));
  }
  assert.equal(L.mouthFrom("v1;src=kokoro;100:/wCAAQ==\0").n, 1);
  assert.equal(L.mouthFrom("v1;100:/wCAAQ==").n, 1);
  const t = (n, v, fps = 100) => ({ fps, n, level: new Float32Array(n).fill(v), open: new Float32Array(n).fill(v),
    wide: new Float32Array(n).fill(v), round: new Float32Array(n).fill(v) });
  const audio = t(10, 0.25), m = L.merge(audio, t(8, 0.75));
  assert.equal(m.n, 10); assert.equal(m.level, audio.level);
  assert.deepEqual([m.open[7], m.open[8], m.round[9]], [0.75, 0, 0]);
  assert.equal(L.merge(audio, t(13, 0.75)).n, 10);
  assert.equal(L.merge(audio, t(7, 0.75)).wide[0], 0.75);
  for (const other of [t(6, 0.75), t(14, 0.75), null, undefined, t(10, 0.75, 50), t(0, 0.75)]) {
    assert.equal(L.merge(audio, other), audio);
  }
  assert.equal(L.MERGE_SLACK, 3);
  const kt = readFileSync(join(REPO, "jarvis-client", "app", "src", "main", "java", "com", "jarvis", "client",
    "audio", "LipSync.kt"), "utf8");
  assert.match(kt, new RegExp(`const val MERGE_SLACK = ${L.MERGE_SLACK}\\b`));
});

/* ── Cheap enough ─────────────────────────────────────────────────────────── */

check("a 10 s reply analyses in well under 50 ms", () => {
  const all = Object.values(clips).map((c) => c.samples);
  const total = new Float32Array(240000);
  for (let p = 0, k = 0; p < total.length; k++) {
    const s = all[k % all.length], take = Math.min(s.length, total.length - p);
    total.set(s.subarray(0, take), p); p += take;
  }
  const times = [];
  for (let r = 0; r < 5; r++) {
    const t0 = process.hrtime.bigint();
    L.analyse(total, 24000);
    times.push(Number(process.hrtime.bigint() - t0) / 1e6);
  }
  console.log(`      10 s at 24 kHz: first ${times[0].toFixed(1)} ms, best ${Math.min(...times).toFixed(1)} ms`);
  assert.ok(Math.min(...times) < 50, `best of 5: ${Math.min(...times).toFixed(1)} ms`);
});

/* ── The phone's fixture ──────────────────────────────────────────────────── */

check("the phone's golden fixture is fresh (tools/gen_lipsync.py --check)", () => {
  for (const py of ["python3", "python"]) {
    try {
      execFileSync(py, [join(REPO, "tools", "gen_lipsync.py"), "--check"], { stdio: "pipe" });
      return;
    } catch (e) {
      if (e.code === "ENOENT") continue;
      throw new Error(String(e.stderr || e.message));
    }
  }
  console.log("      (no python here - CI's backend job runs it)");
});

if (fails.length) {
  console.log(`\n${fails.length} failed: ${fails.join(", ")}`);
  process.exit(1);
}
console.log("\nall lip-sync checks passed");
