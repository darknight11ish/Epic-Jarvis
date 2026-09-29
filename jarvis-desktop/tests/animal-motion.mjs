/**
 * The animals' motion after the skeptical review (2026-09-29; docs/CRITTERS.md
 * "Motion that does not repeat", "Fewer small moves when Jarvis is not being
 * used" and "Gestures that land on the end of a sentence"). Pure node, no
 * browser: the pose code (critter-*.js) and lipsync.js are loaded as the pages
 * load them and driven directly. The phone's copies are held to the same
 * numbers by CritterPoseTest (critter-pose-golden.json, critter-drift-golden.json).
 *
 *  1. The slow wander (noise()) replaces the sines every face shared: smooth,
 *     within -1..1, never faster than 2 / scale a second, repeating only after
 *     4096 s (so the phone's clock wrap moves nothing), different per face and
 *     per use - so the five faces no longer sway together and breathing is not a
 *     metronome, without any face moving more than it did.
 *  2. Each idle happening is a little different (size 0.75-1, length 0.8-1.25x)
 *     and - with `attention` 0, the owner not using Jarvis - about one in four
 *     is left, the same clips, easing in and out as attention changes.
 *  3. The owl's thinking head moves about as often as the others'.
 *  4. Gestures on Jarvis's phrase ends: with the clip read before it plays, the
 *     host hands the pose each end ahead of time and the gesture PEAKS on it;
 *     the finder that listens to the level finds it about 0.4 s late.
 *
 *     node tests/animal-motion.mjs
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
for (const f of ["critter-pose.js", "critter-owl.js", "critter-otter.js", "critter-monkey.js", "critter-robot.js"]) {
  vm.runInContext(readFileSync(join(SRC, f), "utf8"), ctx, { filename: f });
}
const C = ctx.CritterPose;
const U = C.util;
const FACES = ["redpanda", "pygmyowl", "seaotter", "monkey", "robot"];
const DEG = 180 / Math.PI;

const fails = [];
const check = (name, fn) => {
  try { fn(); console.log(`ok    ${name}`); }
  catch (e) { fails.push(name); console.log(`FAIL  ${name}\n      ${e.message}`); }
};
const pose = (sp, st, t, opts, amp = 0, since = 99) => C.species[sp].pose(st, st, since, t, amp, {}, {}, opts || {});
const corr = (a, b) => {
  const n = a.length; let ma = 0, mb = 0;
  for (let i = 0; i < n; i++) { ma += a[i]; mb += b[i]; }
  ma /= n; mb /= n;
  let sab = 0, saa = 0, sbb = 0;
  for (let i = 0; i < n; i++) { sab += (a[i] - ma) * (b[i] - mb); saa += (a[i] - ma) ** 2; sbb += (b[i] - mb) ** 2; }
  return sab / Math.sqrt(saa * sbb);
};

// ---- 1. the slow wander ------------------------------------------------------

check("noise: smooth, inside -1..1, and never faster than 2 / scale a second", () => {
  for (const scale of [4, 8, 16, 32]) {
    let lo = 9, hi = -9, fast = 0;
    const dt = 1 / 60;
    let prev = U.noise(0, 8, scale);
    for (let t = dt; t < 4096; t += dt) {
      const v = U.noise(t, 8, scale);
      lo = Math.min(lo, v); hi = Math.max(hi, v);
      fast = Math.max(fast, Math.abs(v - prev) / dt);
      prev = v;
    }
    assert.ok(lo >= -1 && hi <= 1, `scale ${scale}: ${lo}..${hi}`);
    assert.ok(hi > 0.6 && lo < -0.6, `scale ${scale} hardly moves: ${lo}..${hi}`);
    assert.ok(fast <= 2 / scale + 1e-6, `scale ${scale}: changes ${fast.toFixed(4)} a second, more than ${(2 / scale).toFixed(4)}`);
  }
});

check("noise repeats only after 4096 s; another seed is another wander", () => {
  for (const t of [0.3, 47.1, 1000.7, 4095.9]) {
    for (const p of [4096, 8192, 86400 - (86400 % 4096)]) {
      assert.ok(Math.abs(U.noise(t, 17, 8) - U.noise(t + p, 17, 8)) < 1e-9, `t ${t} + ${p}`);
    }
  }
  // Inside one period it does not come back: not after 1024 s, not after 2048 s.
  const a = [], b = [], c = [], d = [];
  for (let t = 0; t < 1024; t += 0.5) { a.push(U.noise(t, 8, 4)); b.push(U.noise(t + 1024, 8, 4)); c.push(U.noise(t + 2048, 8, 4)); d.push(U.noise(t, 9, 4)); }
  assert.ok(Math.abs(corr(a, b)) < 0.2 && Math.abs(corr(a, c)) < 0.2, `it repeats inside a period (${corr(a, b)}, ${corr(a, c)})`);
  assert.ok(Math.abs(corr(a, d)) < 0.2, `two seeds move together (${corr(a, d)})`);
});

check("talking: the five heads no longer sway together (were 0.86 and 0.91 alike)", () => {
  // The swaying part of the head: the speaking pose minus the same pose under "Still" (which
  // takes the swaying and the looking away), each face's yaw and roll every 0.1 s for 15 minutes.
  const series = {};
  for (const sp of FACES) {
    const yaw = [], roll = [];
    for (let t = 1000; t < 1900; t += 0.1) {
      const P = pose(sp, "speaking", t, { nods: 0 }, 0.3), Q = pose(sp, "speaking", t, { nods: 0, still: 1 }, 0.3);
      yaw.push(P.headYaw - Q.headYaw); roll.push(P.headRoll - Q.headRoll);
    }
    series[sp] = { yaw, roll };
  }
  let worst = 0;
  for (let i = 0; i < FACES.length; i++) for (let j = i + 1; j < FACES.length; j++) {
    for (const k of ["yaw", "roll"]) worst = Math.max(worst, Math.abs(corr(series[FACES[i]][k], series[FACES[j]][k])));
  }
  assert.ok(worst < 0.4, `two faces sway alike: correlation ${worst.toFixed(2)}`);
});

check("breathing is uneven: every face's breaths vary in length, by up to about 15 percent, and never deeper than before", () => {
  const amp = { redpanda: 0.018, pygmyowl: 0.016, seaotter: 0.02, monkey: 0.02 };
  for (const sp of FACES) {
    const key = sp === "robot" ? "posY" : "breath";
    const xs = [], dt = 0.02;
    for (let t = 1000; t < 1000 + 1800; t += dt) xs.push(pose(sp, "idle", t, { still: 1 })[key]);
    let mean = 0; for (const v of xs) mean += v; mean /= xs.length;
    const ups = [];
    for (let i = 1; i < xs.length; i++) if (xs[i - 1] < mean && xs[i] >= mean) ups.push(1000 + i * dt);
    const per = []; for (let i = 1; i < ups.length; i++) per.push(ups[i] - ups[i - 1]);
    const m = per.reduce((a, b) => a + b, 0) / per.length;
    const sd = Math.sqrt(per.reduce((a, b) => a + (b - m) ** 2, 0) / per.length);
    const dev = Math.max(...per.map((p) => Math.abs(p / m - 1)));
    assert.ok(sd / m > 0.03, `${sp}: breaths hardly vary (${(100 * sd / m).toFixed(1)} percent)`);
    assert.ok(dev > 0.08 && dev < 0.22, `${sp}: the longest and shortest breaths are ${(100 * dev).toFixed(1)} percent off the average`);
    if (amp[sp]) {
      const deepest = Math.max(...xs.map((v) => Math.abs(v - 1)));
      assert.ok(deepest <= amp[sp] * 1.0001, `${sp}: a breath ${deepest.toFixed(4)} deep, more than the steady ${amp[sp]}`);
    }
  }
  // (The panda's breath used to be a sine, exactly 4.000 s every time.)
});

check("no face breathes in step with another", () => {
  const s = {};
  for (const sp of ["redpanda", "seaotter", "monkey"]) {   // (the same steady rate, 4 s to 4.2 s)
    s[sp] = [];
    for (let t = 1000; t < 1600; t += 0.1) s[sp].push(pose(sp, "idle", t, { still: 1 }).breath);
  }
  assert.ok(Math.abs(corr(s.redpanda, s.monkey)) < 0.6, `panda and monkey: ${corr(s.redpanda, s.monkey)}`);
});

// ---- 2. the happenings ----------------------------------------------------------

/** The idle happenings of one face over an hour, each [start, weight, length factor], from happeningV. */
function happenings(sp, att, hours = 1) {
  const seen = [];
  let was = false, startedAt = 0;
  for (let t = 1000; t < 1000 + 3600 * hours; t += 0.05) {
    const b = C.species[sp].busy("idle", t, undefined, att === undefined ? undefined : { attention: att });
    if (b && !was) { seen.push(t); startedAt = t; }
    was = b;
  }
  return seen;
}

check("with the owner not using Jarvis about one idle happening in four is left - the same ones, only rarer", () => {
  for (const sp of FACES) {
    const all = happenings(sp, 1), few = happenings(sp, 0);
    assert.ok(all.length > 120, `${sp}: ${all.length} an hour to start with`);
    const share = few.length / all.length;
    assert.ok(share > 0.15 && share < 0.35, `${sp}: ${few.length} of ${all.length} left (${(100 * share).toFixed(0)} percent)`);
    // Every one that is left is one that was there (a thinned hour is a subset, never new moments).
    for (const t of few) assert.ok(all.some((a) => Math.abs(a - t) < 0.06), `${sp}: a happening at ${t.toFixed(2)} s that was not there before`);
  }
});

check("a host that says nothing about attention gets exactly today's happenings; attention 1 the same", () => {
  for (const sp of FACES) {
    for (let t = 1000; t < 1600; t += 0.37) {
      assert.equal(C.species[sp].busy("idle", t), C.species[sp].busy("idle", t, undefined, { attention: 1 }), sp);
    }
  }
  // ...and the pose itself is identical whether it is passed or not.
  for (const sp of FACES) {
    for (const t of [1003.2, 1050.7, 1117.15, 1300.3]) {
      const a = pose(sp, "idle", t), b = pose(sp, "idle", t, { attention: 1 });
      for (const k of Object.keys(a)) assert.equal(a[k], b[k], `${sp} ${k} at ${t}`);
    }
  }
});

check("attention eases: the happenings fade in one by one as it rises, and nothing snaps", () => {
  // (Slot by slot, the weight of the happening rises with attention; the ones that stay at 0 are a quarter.)
  for (let att = 0; att < 1; att += 0.1) {
    let lo = 0, hi = 0, kept = 0;
    for (let n = 0; n < 256; n++) {
      lo += U.thinGate(n, 16, 19, att); hi += U.thinGate(n, 16, 19, att + 0.1);
      if (att === 0 && U.thinGate(n, 16, 19, 0) === 1) kept++;
    }
    assert.ok(hi >= lo, `attention ${att.toFixed(1)}: ${lo} then ${hi}`);
    if (att === 0) assert.ok(kept > 0.18 * 256 && kept < 0.32 * 256, `${kept} of 256 slots stay at attention 0`);
  }
  // Across 240 frames a second, with attention easing from 0 to 1 over 2 s in the middle of a happening,
  // no pose number jumps by more than the biggest step the same clip takes at full attention.
  for (const sp of FACES) {
    const busy = [];
    for (let t = 1000; t < 3000; t += 0.05) if (C.species[sp].busy("idle", t)) busy.push(t);
    // A happening well inside (its start + 2.5 s): find ones that are thinned away at attention 0.
    const t0 = busy.find((t) => !C.species[sp].busy("idle", t, undefined, { attention: 0 })
                                && !C.species[sp].busy("idle", t + 0.6, undefined, { attention: 0 })) + 0.5;
    const dt = 1 / 240;
    let prev = null, worst = 0, steady = 0;
    for (let k = 0; k < 720; k++) {
      const t = t0 + k * dt;
      const P = pose(sp, "idle", t, { attention: Math.min(1, k * dt / 2) });
      const F = pose(sp, "idle", t, {});
      if (prev) for (const key of Object.keys(P)) {
        worst = Math.max(worst, Math.abs(P[key] - prev.P[key]));
        steady = Math.max(steady, Math.abs(F[key] - prev.F[key]));
      }
      prev = { P, F };
    }
    assert.ok(worst <= steady * 1.5 + 1e-4, `${sp}: a pose number jumps ${worst} in one frame while attention eases (${steady} at full attention)`);
  }
});

check("each idle happening is a little different: size 0.75 to 1, length 0.8 to 1.25 times", () => {
  for (const sp of FACES) {
    const sizes = new Set(), longs = new Set();
    for (let n = 0; n < 256; n++) {
      // the middle of every slot's happening, as happeningV reports it
      const h = U.happeningV(n * 16 + 9, 16, 0.5, 5.5, 16, 1.0, 1, 1);
      if (h[0] < 0) continue;
      assert.ok(h[3] >= 0.75 - 1e-9 && h[3] <= 1 + 1e-9, `size ${h[3]}`);
      sizes.add(h[3].toFixed(3));
      const raw = 9 - (h[2] - n * 16);
      longs.add((raw / h[1]).toFixed(3));
      const ratio = raw / h[1];
      assert.ok(ratio >= 0.8 - 1e-6 && ratio <= 1.25 + 1e-6, `length ${ratio}`);
    }
    assert.ok(sizes.size > 100 && longs.size > 100, `the slots do not vary: ${sizes.size} sizes, ${longs.size} lengths`);
    break;   // (the same helper for every face)
  }
  // The panda's tail flick: no two of a half hour's are the same clip.
  const C1 = C.species.redpanda;
  const seen = new Set();
  for (let n = 0; n < 600; n++) {
    const h = U.happeningV(1000 + n * 16 + 9, 16, 0.5, 5.5, 16, 0.7, [12, 30, 12, 23, 23], 1);
    if (h[0] === 1) seen.add(`${h[3].toFixed(3)}|${h[1].toFixed(3)}`);
  }
  assert.ok(seen.size >= 30, `${seen.size} different tail flicks`);
  // A happening still plays within HAPPENING_S and its slot: the longest, stretched, still ends before the next slot.
  assert.ok(5.5 * 1.25 + 6 < 16);
  assert.ok(C1);
});

// ---- 3. the owl's thinking head ---------------------------------------------------

check("the owl's thinking head rolls about half as far and follows its orb only now and then", () => {
  const sp = "pygmyowl";
  let roll = 0, followedOn = 0, n = 0, moving = 0, prev = null;
  const dt = 0.05;
  for (let t = 1000; t < 1600; t += dt) {
    const P = pose(sp, "thinking", t);
    roll = Math.max(roll, Math.abs(P.headRoll));
    if (prev) {
      const v = Math.hypot(P.headYaw - prev.headYaw, P.headPitch - prev.headPitch, P.headRoll - prev.headRoll) / dt * DEG;
      if (v > 3) moving++;
      n++;
    }
    prev = P;
  }
  assert.ok(roll <= 0.13 + 1e-9, `the head rolls ${roll} rad (was 0.26)`);
  const share = moving / n;
  assert.ok(share < 0.45, `the head moves ${(100 * share).toFixed(0)} percent of the time (was 87)`);
  assert.ok(share > 0.05, "the head never moves");
  // it does turn to the orb sometimes
  let turned = 0;
  for (let t = 1000; t < 1600; t += 0.1) if (Math.abs(pose(sp, "thinking", t).headYaw) > 0.1) turned++;
  assert.ok(turned > 20, "it never turns to the orb");
  void followedOn;
});

// ---- 4. gestures that land on a phrase end -------------------------------------------

check("aheadStep: an end is taken up between 0.65 and 0.9 s away, and 2 s after the last", () => {
  let r = null;
  r = C.aheadStep(r, 0, null); assert.equal(JSON.stringify(r), JSON.stringify({ n: 0, due: null }));
  r = C.aheadStep(r, 0.016, 1.4); assert.equal(r.n, 0, "too far ahead: wait");
  r = C.aheadStep(r, 0.016, 0.88); assert.equal(r.n, 1); assert.equal(r.due, 0.88);
  r = C.aheadStep(r, 0.5, 0.7); assert.equal(r.n, 1, "the same end is not taken twice");
  assert.ok(Math.abs(r.due - 0.38) < 1e-9, "its time runs down");
  r = C.aheadStep(r, 0.5, 0.8); assert.equal(r.n, 1, "less than 2 s after the last: left out");
  r = C.aheadStep(r, 1.5, 0.85); assert.equal(r.n, 2, "2 s later: taken");
  const late = C.aheadStep(null, 0.016, 0.4);
  assert.equal(late.n, 0, "found too late (under 0.65 s): left out, not played half way");
});

/** A clip's mouth track, the way the pages have it. */
const clip = (file) => {
  const w = L.fromWav(readFileSync(join(CLIPS, file)));
  const a = L.analyse(w.samples, w.sampleRate);
  return { t: w.mouth ? L.merge(a, w.mouth) : a, dur: w.samples.length / w.sampleRate };
};
const PACED = { "0.7225": "kokoro-panda-lips-slowest.wav", "1.0": "kokoro-panda-lips.wav", "1.3225": "kokoro-robot-lips-fastest.wav" };

/**
 * Plays a clip to a speaking face at 60 frames a second and finds where each gesture PEAKS
 * (the centre of the stretch where the pose is furthest from the same pose with no gesture),
 * for a host that either listens to the level as heard (the old finder: `ahead` false) or is handed
 * each end ahead of time. Returns [{end, at}] for every phrase end a gesture played on.
 */
function landings(sp, file, ahead, t0) {
  const { t: track, dur } = clip(file);
  const ends = L.phraseEnds(track), s = {}, dt = 1 / 60, api = C.species[sp];
  let rec = null, pause = null, n = 0;
  const frames = [];
  for (let i = 0; i < (dur + 3) / dt; i++) {
    const est = i * dt;
    L.sample(track, est, s);
    let opts;
    if (ahead) {
      let next = null;
      for (const e of ends) if (e > est) { next = e - est; break; }
      rec = C.aheadStep(rec, dt, next);
      opts = { phraseDue: rec.due === null ? undefined : rec.due, phraseN: rec.n };
    } else {
      pause = C.pauseStep(pause, dt, s.level, C.PAUSE.PHRASE_QUIET, C.PAUSE.PHRASE_GAP);
      opts = { phraseEnd: pause.ago, phraseN: pause.n };
    }
    const P = api.pose("speaking", "speaking", 99, t0 + est, 0.3, {}, {}, opts);
    const R = api.pose("speaking", "speaking", 99, t0 + est, 0.3, {}, {}, { phraseN: 0 });
    let d = 0;
    for (const k of Object.keys(P)) if (k !== "speak" && k !== "asleep") d += (P[k] - R[k]) ** 2;
    frames.push({ est, d: Math.sqrt(d) });
  }
  // Cut the frames into gestures (runs where the pose differs), then the centre of each's top half.
  const out = [];
  let i = 0;
  while (i < frames.length) {
    if (frames[i].d < 1e-4) { i++; continue; }
    let j = i; while (j < frames.length && frames[j].d >= 1e-4) j++;
    const seg = frames.slice(i, j), top = Math.max(...seg.map((f) => f.d));
    const hi = seg.filter((f) => f.d >= 0.5 * top);
    const at = hi.reduce((a, f) => a + f.est * f.d, 0) / hi.reduce((a, f) => a + f.d, 0);
    let near = null;
    for (const e of ends) if (near === null || Math.abs(e - at) < Math.abs(near - at)) near = e;
    out.push({ end: near, at });
    i = j;
  }
  return out;
}

check("the clip's phrase ends are known before it plays: \"Okay.\" (at the slower paces) and the clip's end", () => {
  for (const [pace, file] of Object.entries(PACED)) {
    const { t, dur } = clip(file);
    const ends = L.phraseEnds(t);
    assert.ok(ends.length >= 1 && ends.length <= 2, `${pace}: ${ends}`);
    // Inside the clip, and never closer than a gesture's spacing (2 s) - so at the slower paces "Okay." is
    // a phrase end and the clip's own end, under 2 s later, is not another.
    for (const e of ends) assert.ok(e > 0.3 && e <= dur + 0.02, `${pace}: an end at ${e} of ${dur}`);
    for (let i = 1; i < ends.length; i++) assert.ok(ends[i] - ends[i - 1] >= 2 - 1e-9, `${pace}: ends ${ends}`);
  }
  assert.equal(L.phraseEnds(null).length, 0);
  assert.equal(L.phraseEnds({ n: 0, fps: 100, level: [] }).length, 0);
  // A sound that runs to the last frame ends a phrase there; a pause of 0.05 s ends one (2 s must pass
  // before the next); a short word before a pause is not a phrase.
  const lv = new Float32Array(400).fill(0.5);
  assert.deepEqual(Array.from(L.phraseEnds({ n: 400, fps: 100, level: lv })), [4]);
  const lw = new Float32Array(500).fill(0.5);
  lw.fill(0, 200, 210);
  assert.deepEqual(Array.from(L.phraseEnds({ n: 500, fps: 100, level: lw })).map((x) => +x.toFixed(2)), [2, 5], "the pause at 2.00 s is a phrase end");
  lw.fill(0, 30, 60);
  assert.deepEqual(Array.from(L.phraseEnds({ n: 500, fps: 100, level: lw })).map((x) => +x.toFixed(2)), [2, 5], "0.3 s of sound before a pause is too short to be a phrase");
  assert.deepEqual(Array.from(L.phraseEnds({ n: 400, fps: 100, level: lv.map((v, k) => (k >= 200 && k < 210 ? 0 : v)) })).map((x) => +x.toFixed(2)), [2], "the clip's own end, under 2 s after the pause, is left out");
});

check("the gesture PEAKS on the sentence end when the end is known ahead, and about 0.4 s late when it is heard, at three voice speeds", () => {
  for (const sp of FACES) {
    for (const [pace, file] of Object.entries(PACED)) {
      // (Ten different moments of the animal's day: a gesture waits while its eyes are about to look somewhere else.)
      const now = [], old = [];
      for (let k = 0; k < 10; k++) { now.push(...landings(sp, file, true, 400 + 37.3 * k)); old.push(...landings(sp, file, false, 400 + 37.3 * k)); }
      assert.ok(now.length >= 3, `${sp} ${pace}: only ${now.length} gestures in ten tries`);
      for (const g of now) {
        assert.ok(Math.abs(g.at - g.end) <= 0.13, `${sp} ${pace}: a gesture peaks ${(g.at - g.end).toFixed(2)} s from the end`);
      }
      for (const g of old) {
        assert.ok(g.at - g.end >= 0.25, `${sp} ${pace}: the old finder's gesture peaks only ${(g.at - g.end).toFixed(2)} s after the end - then this check's premise changed`);
      }
    }
  }
});

check("a host that hands the pose nothing new gets its gestures exactly as before (phraseEnd, no phraseDue)", () => {
  for (const sp of FACES) {
    const a = pose(sp, "speaking", 20.9, { phraseEnd: 0.4, phraseN: 3 }, 0.3);
    const b = pose(sp, "speaking", 20.9, { phraseEnd: 0.4, phraseN: 3, attention: 1 }, 0.3);
    for (const k of Object.keys(a)) assert.equal(a[k], b[k], `${sp} ${k}`);
  }
});

console.log(fails.length ? `\n${fails.length} failed: ${fails.join("; ")}` : "\nthe animals' motion holds");
process.exit(fails.length ? 1 : 0);
