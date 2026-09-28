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
  for (const k of ["analyse", "sample", "fromWav", "pack", "unpack"]) assert.equal(typeof L[k], "function", k);
  assert.equal(L.FPS, 100);
  assert.ok(L.LEAD_S > 0 && L.LEAD_S <= 0.1, `LEAD_S ${L.LEAD_S}`);
});

check("the Kotlin copy has the same FPS and LEAD_S", () => {
  const kt = readFileSync(join(REPO, "jarvis-client", "app", "src", "main", "java", "com", "jarvis", "client",
    "audio", "LipSync.kt"), "utf8");
  assert.match(kt, new RegExp(`const val FPS = ${L.FPS}\\b`));
  assert.match(kt, new RegExp(`const val LEAD_S = ${L.LEAD_S}f\\b`));
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

check("wide and round are never both high", () => {
  for (const [name, c] of Object.entries(clips)) {
    for (let i = 0; i < c.track.n; i++) {
      assert.ok(Math.min(c.track.wide[i], c.track.round[i]) < 0.3, `${name} frame ${i}`);
    }
  }
});

/* ── sample(): the playback clock plus the lead ──────────────────────────── */

check("sample() reads LEAD_S ahead, interpolates, and is all zeros outside", () => {
  const n = 20, ramp = Float32Array.from({ length: n }, (_, i) => i / (n - 1));
  const t = { fps: 100, n, level: ramp, open: ramp, wide: new Float32Array(n), round: new Float32Array(n) };
  assert.equal(L.sample(null, 0.1), null);
  const at0 = L.sample(t, 0);
  assert.ok(Math.abs(at0.open - (L.LEAD_S * 100) / (n - 1)) < 1e-6, "t=0 reads frame LEAD_S*FPS");
  const mid = L.sample(t, 0.075 - L.LEAD_S);
  assert.ok(Math.abs(mid.level - 7.5 / (n - 1)) < 1e-6, "halfway between frames 7 and 8");
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
