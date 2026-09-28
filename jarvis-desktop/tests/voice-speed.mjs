/**
 * The animals at every speed of Jarvis's voice (the voice-speed check,
 * 2026-09-28; docs/LIPSYNC.md "At every pace").
 *
 * The owner can slow Jarvis's voice down or speed it up (an animal's own
 * pace times "How fast Jarvis speaks": 0.7225x to 1.3225x from the apps).
 * The mouth follows the sound at every pace (lipsync.mjs checks the mouth
 * itself on the slowest and fastest committed clips); this checks the two
 * things around it that depend on how fast the words come:
 *
 * - the phrase-end finder (critter-pose.js pauseStep with PHRASE_QUIET),
 *   which the talking gestures land on. The apps speak an answer one
 *   sentence per clip, and back to back two clips leave only about a tenth
 *   of a second of quiet at the normal pace and faster: with the old
 *   PHRASE_QUIET (0.15 s) the finder missed almost all of them;
 * - the robot's eyes, which pulse with the same mouth track: never busier
 *   than the words, and never a jump, at the slowest or the fastest pace.
 *
 * Pure node, no browser.
 */
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { createRequire } from "node:module";
import vm from "node:vm";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const HERE = dirname(fileURLToPath(import.meta.url));
const SRC = join(HERE, "..", "src");
const REPO = join(HERE, "..", "..");
const CLIPS = join(REPO, "jarvis-client", "app", "src", "test", "resources", "lipsync");
const L = createRequire(import.meta.url)(join(SRC, "lipsync.js"));
const ctx = { console };
ctx.globalThis = ctx; ctx.window = ctx;
vm.createContext(ctx);
for (const f of ["critter-pose.js", "critter-robot.js"]) {
  vm.runInContext(readFileSync(join(SRC, f), "utf8"), ctx, { filename: f });
}
const C = ctx.CritterPose;
const P = C.PAUSE;

const fails = [];
const check = (name, fn) => {
  try { fn(); console.log(`ok    ${name}`); }
  catch (e) { fails.push(name); console.log(`FAIL  ${name}\n      ${e.message}`); }
};
const FPS = 60, DT = 1 / FPS;

// The committed clips: "Okay. Maybe Bob made a map." at the slowest pace the
// apps offer (the panda's voice, 0.7225) and the fastest (the robot's, 1.3225),
// each with the PC's mouth chunk - what both apps play.
const PACED = { slowest: "kokoro-panda-lips-slowest.wav", fastest: "kokoro-robot-lips-fastest.wav" };
const track = (file) => {
  const w = L.fromWav(readFileSync(join(CLIPS, file)));
  const a = L.analyse(w.samples, w.sampleRate);
  return { t: L.merge(a, w.mouth), dur: w.samples.length / w.sampleRate };
};

/** A host playing two copies of a clip back to back, 30 ms apart (the
 *  desktop starts the next clip as the last one ends; nothing is fed in
 *  between), running the phrase finder on the level it reads, as
 *  faces.html does. `gap` 0: every pause found, not only one per
 *  PHRASE_GAP. Returns where it found phrase ends, and where each clip ended. */
function play({ t, dur }, quiet, gap = 0) {
  let rec = null, n = 0, now = 0;
  const found = [], ends = [], s = {};
  const step = (lv) => {
    rec = C.pauseStep(rec, DT, lv, quiet, gap);
    now += DT;
    if (rec.n > n) { n = rec.n; found.push(now); }
  };
  for (let c = 0; c < 2; c++) {
    for (let i = 0; i < Math.ceil(dur * FPS); i++) { L.sample(t, i * DT, s); step(s.level); }
    ends.push(now);
    for (let i = 0; i < Math.round(0.03 * FPS); i++) step(0);
  }
  for (let i = 0; i < FPS; i++) step(0);
  return { found, ends };
}

check("PHRASE_QUIET is short enough for the quiet between two fast sentences, the same on the phone", () => {
  assert.equal(P.PHRASE_QUIET, 0.05);
  assert.equal(P.PHRASE_GAP, 2.0, "at most one gesture every 2 s, at any pace");
  const kt = readFileSync(join(REPO, "jarvis-client", "app", "src", "main", "java", "com", "jarvis", "client",
    "face", "CritterPose.kt"), "utf8");
  assert.match(kt, /const val PHRASE_QUIET = 0\.05f\b/);
  assert.match(kt, /const val PHRASE_GAP = 2\.0f\b/);
});

check("between two sentences spoken back to back, a phrase end is found at the slowest and the fastest pace", () => {
  for (const [pace, file] of Object.entries(PACED)) {
    const clip = track(file);
    const { found, ends } = play(clip, P.PHRASE_QUIET);
    for (const e of ends) {
      assert.ok(found.some((x) => x > e - 0.3 && x < e + 0.35),
        `${pace}: nothing found near the end of a sentence at ${e.toFixed(2)} s (found ${found.map((x) => x.toFixed(2))})`);
    }
  }
  // The old 0.15 s missed the fastest pace's sentence ends altogether.
  const old = play(track(PACED.fastest), 0.15);
  assert.ok(!old.found.some((x) => Math.abs(x - old.ends[0]) < 0.35),
    `0.15 s found the fastest pace's sentence end? (${old.found}) then this test's premise changed`);
});

check("...and never inside \"Maybe Bob made a map.\" - only after \"Okay.\" and at the end", () => {
  for (const [pace, file] of Object.entries(PACED)) {
    const clip = track(file);
    const { found, ends } = play(clip, P.PHRASE_QUIET);
    // Where "Okay." stops: the first 60 ms of level-quiet in the clip.
    const s = {};
    let okay = null, run = 0;
    for (let i = 0; i < clip.dur * FPS && okay === null; i++) {
      L.sample(clip.t, i * DT, s);
      run = s.level <= P.OFF && i * DT > 0.2 ? run + 1 : 0;
      if (run >= 0.06 * FPS) okay = i * DT;
    }
    // At the slowest pace "Okay." ends in a real pause; at the fastest the
    // pause is too short to count (and nothing is found there).
    if (pace === "slowest") assert.ok(okay !== null && okay < clip.dur / 2, `${pace}: no pause after "Okay."`);
    const starts = [0, ends[0] + 0.03];
    for (const x of found) {
      const inClip = x < ends[0] + 0.03 ? 0 : 1, local = x - starts[inClip];
      const atOkay = okay !== null && Math.abs(local - okay) < 0.3, atEnd = Math.abs(x - ends[inClip]) < 0.35;
      assert.ok(atOkay || atEnd, `${pace}: a phrase end ${local.toFixed(2)} s into "Okay. Maybe Bob made a map."`);
    }
  }
});

check("the robot's eyes pulse with the words at every pace: no busier than the syllables, never a jump", () => {
  const R = C.species.robot;
  const look = { x: 0, y: 0, w: 0 };
  for (const [pace, file] of Object.entries(PACED)) {
    const { t, dur } = track(file);
    const s = {};
    let prev = null, step = 0, peaks = 0, low = 1, armed = false;
    for (let i = 0; i * DT < dur; i++) {
      // Well into speaking, so the pose's speak weight is 1.
      const Pz = R.pose("speaking", "speaking", 30 + i * DT, 100 + i * DT, 0.3, look, { past: [] }, {});
      L.sample(t, i * DT, s);
      const pulse = R.uniforms(Pz, s).uEyes2[3];
      assert.ok(Math.abs(pulse - Math.min(1, s.open + 0.3 * s.wide)) < 1e-6, `${pace}: the pulse is not the mouth track's`);
      if (prev !== null) step = Math.max(step, Math.abs(pulse - prev));
      prev = pulse;
      if (pulse > 0.3) { if (!armed || low < 0.15) peaks++; armed = true; low = 1; } else if (armed) low = Math.min(low, pulse);
    }
    const rate = peaks / dur;
    // Measured on 196 real clips at 0.5x to 2x: 1.3 to 3.0 pulses a second,
    // the biggest 60 Hz step 0.43 at every pace.
    assert.ok(rate > 1 && rate < 3.5, `${pace}: ${rate.toFixed(2)} pulses a second`);
    assert.ok(step < 0.5, `${pace}: a 60 Hz frame steps the pulse by ${step.toFixed(2)}`);
  }
});

console.log(fails.length ? `\n${fails.length} failed: ${fails.join("; ")}` : "\nthe animals hold up at every voice speed");
process.exit(fails.length ? 1 : 0);
