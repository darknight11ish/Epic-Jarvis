/**
 * The animals' painted eyelids (owner, 2026-09-29; docs/CRITTERS.md "Painted
 * eyelids"): a lid of the surrounding fur laid over the top of each eye by the
 * shader (`uLid`: how far down, and its slope), driven by the pose.
 *
 * What the owner asked for, and what this holds in place:
 *   - idle, listening, thinking, speaking: NO lid (as before);
 *   - waiting on you: a level, attentive lid (0.2), eased in, nothing cute;
 *   - something went wrong: a sloped, worried lid (0.42, slope 1), eased in;
 *   - dozing and asleep: a heavy, level lid (0.55) that comes down as the
 *     animal nods off and lifts as it wakes, in step with the existing
 *     wake/sleep piece;
 *   - a lid is a SETTLED LOOK, not a movement: it adds no idle motion, never
 *     jumps (checked frame by frame at 240 a second), is the same under calm
 *     and Still (they quieten motion, not this look), and a crisis-help
 *     moment (`serious`) leaves the animal neutral - no lid at all;
 *   - blinks still close the eye all the way, lid or not;
 *   - hello and goodbye leave the lid alone; the robot has none.
 * Part 1 is pure node (the pose code, loaded as the pages load it). Part 2
 * opens the real faces.html with Playwright and looks at the pixels: with a
 * lid of nothing the picture is exactly the old one, and a lid covers the
 * amount it is asked to.
 *
 *     node tests/animal-lids.mjs
 */
import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import { createRequire } from "node:module";
import { fileURLToPath } from "node:url";

const HERE = path.dirname(fileURLToPath(import.meta.url));
const SRC = path.join(HERE, "..", "src");
const require = createRequire(import.meta.url);
for (const f of ["critter-pose.js", "critter-owl.js", "critter-otter.js", "critter-monkey.js", "critter-robot.js"]) require(path.join(SRC, f));
const C = globalThis.CritterPose;
const ANIMALS = ["redpanda", "pygmyowl", "seaotter", "monkey"];
const STATES = ["idle", "listening", "thinking", "speaking", "approval", "standby", "error", "banked"];
const WANT = { idle: [0, 0], listening: [0, 0], thinking: [0, 0], speaking: [0, 0], approval: [0.2, 0], error: [0.42, 1], banked: [0.55, 0], standby: [0.55, 0] };
const asleep9 = [{ state: "standby", gap: 9, amp: 0 }, { state: "idle", gap: 20, amp: 0 }];
const awakeFrom = (s, amp = 0) => [{ state: s, gap: 20, amp }, { state: "standby", gap: 9, amp: 0 }];
const ampOf = (s) => (s === "speaking" ? 0.5 : s === "listening" || s === "approval" ? 0.28 : 0);

const fails = [];
const check = async (name, fn) => {
  try { await fn(); console.log(`ok    ${name}`); }
  catch (e) { fails.push(name); console.log(`FAIL  ${name}\n      ${e.message}`); }
};
const near = (a, b, eps, msg) => assert.ok(Math.abs(a - b) <= eps, `${msg}: ${a} is not within ${eps} of ${b}`);
/** The lid the pose draws: [how far down, slope]. */
const lidOf = (id, state, prev, since, t, hist, opts, amp = ampOf(state), look = {}) => {
  const a = C.species[id];
  return a.uniforms(a.pose(state, prev, since, t, amp, look, hist, opts)).uLid;
};
const eyeOf = (id, state, prev, since, t, hist, opts, amp = ampOf(state)) => {
  const a = C.species[id];
  return a.uniforms(a.pose(state, prev, since, t, amp, {}, hist, opts)).uFace;
};
const FRAME = 1 / 240;

// ---- Part 1: the pose ---------------------------------------------------------------

await check("the four animals send a lid, the robot none", () => {
  for (const id of ANIMALS) {
    const u = C.species[id].uniforms(C.species[id].pose("idle", "idle", 30, 5, 0, {}, {}, {}));
    assert.ok(Array.isArray(u.uLid) && u.uLid.length === 2, `${id}: no uLid`);
    assert.ok(C.species[id].KEYS.includes("lid") && C.species[id].KEYS.includes("lidSlope"), `${id}: no lid pose numbers`);
  }
  const r = C.species.robot;
  assert.equal(r.uniforms(r.pose("error", "error", 30, 5, 0, {}, {}, {})).uLid, undefined, "the robot has no eyelids");
  assert.ok(!r.KEYS.includes("lid"));
});

await check("settled, every state has its own lid: none awake, level when waiting, sloped at an error, heavy dozing and asleep", () => {
  for (const id of ANIMALS) for (const s of STATES) {
    for (const t of [0, 3.7, 41.9, 300.25, 2000.5, 86400.25]) {
      const l = lidOf(id, s, s, 30, t);
      near(l[0], WANT[s][0], 1e-6, `${id} ${s} t=${t} lid`);
      near(l[1], WANT[s][1], 1e-6, `${id} ${s} t=${t} slope`);
    }
  }
});

await check("idle, listening, thinking and speaking never have a lid, over half an hour, looking about and talking", () => {
  for (const id of ANIMALS) for (const s of ["idle", "listening", "thinking", "speaking"]) {
    for (let t = 0; t < 1800; t += 0.5) {
      const l = lidOf(id, s, s, 1e6, t, undefined, { variety: 1, cute_moments: 1 }, ampOf(s), { x: Math.sin(t), y: Math.cos(t), w: 0.6 });
      assert.ok(l[0] === 0 && l[1] === 0, `${id} ${s} t=${t}: lid ${l}`);
    }
  }
});

await check("a settled lid is a look, not a motion: it does not move at all, over ten minutes, breathing and glancing", () => {
  for (const id of ANIMALS) for (const s of ["approval", "error", "banked", "standby"]) {
    let lo = 9, hi = -9, slo = 9, shi = -9;
    for (let t = 0; t < 600; t += 0.25) {
      const l = lidOf(id, s, s, 1e6, t, undefined, {});
      lo = Math.min(lo, l[0]); hi = Math.max(hi, l[0]); slo = Math.min(slo, l[1]); shi = Math.max(shi, l[1]);
    }
    assert.ok(hi - lo < 1e-9 && shi - slo < 1e-9, `${id} ${s}: the lid moved (${lo}..${hi}, slope ${slo}..${shi})`);
  }
});

await check("waiting on you and an error arrive eased: the lid and its slope glide in over about a second, never a jump (240 a second)", () => {
  for (const id of ANIMALS) for (const s of ["approval", "error"]) {
    let prev = null, worst = 0, worstS = 0;
    const seen = [];
    for (let x = 0; x <= 4; x += FRAME) {
      const l = lidOf(id, s, "idle", x, 50 + x, { prevAmp: 0 }, {}, ampOf(s));
      if (prev) { worst = Math.max(worst, Math.abs(l[0] - prev[0])); worstS = Math.max(worstS, Math.abs(l[1] - prev[1])); }
      prev = l; seen.push(l);
    }
    assert.ok(seen[0][0] < 0.005 && seen[0][1] < 0.005, `${id} ${s}: starts at ${seen[0]}, not from no lid`);
    assert.ok(worst < 0.006 && worstS < 0.012, `${id} ${s}: a jump of ${worst} / ${worstS} in one frame`);
    // Mostly there by 1 s (three half-lives), all but there by 2.5 s, and never past its amount.
    const at = (x) => seen[Math.round(x / FRAME)];
    assert.ok(at(1.0)[0] > 0.85 * WANT[s][0] && at(1.0)[0] <= WANT[s][0] + 1e-6, `${id} ${s}: ${at(1.0)} at 1 s`);
    assert.ok(at(0.15)[0] < 0.6 * WANT[s][0], `${id} ${s}: already ${at(0.15)} at 0.15 s - not eased`);
    near(at(3.9)[0], WANT[s][0], 0.002, `${id} ${s} at 3.9 s`);
    near(at(3.9)[1], WANT[s][1], 0.005, `${id} ${s} slope at 3.9 s`);
    // ...and only ever growing (no wobble, no overshoot) on the way in.
    for (let i = 1; i < seen.length; i++) assert.ok(seen[i][0] >= seen[i - 1][0] - 1e-9, `${id} ${s}: the lid went back up at ${i * FRAME}`);
  }
});

await check("no change of state ever makes the lid jump (all 56 changes, then the same from asleep and into it)", () => {
  for (const id of ANIMALS) for (const a of STATES) for (const b of STATES) {
    if (a === b) continue;
    let prev = null;
    for (let x = 0; x <= 4; x += FRAME) {
      const l = lidOf(id, b, a, x, 90 + x, { prevAmp: ampOf(a) }, { variety: 1 }, ampOf(b));
      if (prev) {
        assert.ok(Math.abs(l[0] - prev[0]) < 0.008 && Math.abs(l[1] - prev[1]) < 0.02, `${id} ${a}->${b} at ${x.toFixed(3)} s: ${prev} -> ${l}`);
        assert.ok(l[0] >= 0 && l[0] <= 1 && l[1] >= -1 && l[1] <= 1, `${id} ${a}->${b}: out of range ${l}`);
      }
      prev = l;
    }
  }
});

await check("nodding off: the lid comes down with the eyes, from the look it had, to the heavy one - in step with the wake/sleep piece", () => {
  for (const id of ANIMALS) for (const from of ["idle", "approval", "error"]) {
    const h = { past: awakeFrom(from, ampOf(from)) };
    const start = lidOf(id, "standby", from, 0, 140, h, {}, 0);
    near(start[0], WANT[from][0], 0.01, `${id} from ${from}: the lid at the moment it starts to nod off`);
    near(start[1], WANT[from][1], 0.02, `${id} from ${from}: the slope at the start`);
    let prev = start, upStream = 0;
    for (let x = 0; x <= 3.6; x += FRAME) {
      const l = lidOf(id, "standby", from, x, 140 + x, h, {}, 0);
      assert.ok(Math.abs(l[0] - prev[0]) < 0.008 && Math.abs(l[1] - prev[1]) < 0.02, `${id} from ${from} at ${x.toFixed(3)} s: ${prev} -> ${l}`);
      prev = l;
    }
    near(prev[0], 0.55, 0.002, `${id} from ${from}: heavy when asleep`);
    near(prev[1], 0, 0.005, `${id} from ${from}: level when asleep`);
    // Half way down (1.2 s) it is part way, not there yet, and not still where it began (when it began with none).
    const mid = lidOf(id, "standby", from, 1.2, 141.2, h, {}, 0);
    if (from === "idle") assert.ok(mid[0] > 0.1 && mid[0] < 0.53, `${id}: ${mid} 1.2 s into nodding off`);
    // The lid follows the eyes: shut eyes, heavy lid; wide eyes, none of it.
    const eyes = eyeOf(id, "standby", "idle", 3.4, 143.4, { past: awakeFrom("idle") }, {}, 0)[0];
    assert.ok(eyes < 0.01, `${id}: eyes ${eyes} shut at 3.4 s`);
  }
});

await check("waking: the heavy lid lifts a little after the eyes open, into no lid, a level one or a worried one", () => {
  for (const id of ANIMALS) for (const to of ["idle", "listening", "approval", "error", "banked"]) {
    let prev = null;
    const first = lidOf(id, to, "standby", 0, 120, { past: asleep9 }, {}, ampOf(to));
    near(first[0], 0.55, 0.01, `${id} into ${to}: heavy as it starts to wake`);
    for (let x = 0; x <= 3.4; x += FRAME) {
      const l = lidOf(id, to, "standby", x, 120 + x, { past: asleep9 }, {}, ampOf(to));
      if (prev) assert.ok(Math.abs(l[0] - prev[0]) < 0.008 && Math.abs(l[1] - prev[1]) < 0.02, `${id} into ${to} at ${x.toFixed(3)} s: ${prev} -> ${l}`);
      prev = l;
    }
    near(prev[0], WANT[to][0], 0.002, `${id} into ${to}: the lid it settles to`);
    near(prev[1], WANT[to][1], 0.005, `${id} into ${to}: the slope it settles to`);
    // The eyes come first: by 0.7 s they are open, and the lid has barely started to lift at 0.25 s.
    const early = lidOf(id, to, "standby", 0.25, 120.25, { past: asleep9 }, {}, ampOf(to));
    if (to === "idle") assert.ok(early[0] > 0.5, `${id}: the lid was already ${early[0]} at 0.25 s (it should wait for the eyes)`);
    if (to === "idle") assert.ok(lidOf(id, "idle", "standby", 1.5, 121.5, { past: asleep9 }, {})[0] < 0.005, `${id}: still a lid 1.5 s after waking`);
  }
});

await check("a crisis-help moment (serious) keeps the animal neutral: no lid in any state, eased by the host's weight, waking and nodding off too", () => {
  for (const id of ANIMALS) for (const s of STATES) {
    const l = lidOf(id, s, s, 30, 20, undefined, { serious: 1 });
    assert.ok(l[0] === 0 && l[1] === 0, `${id} ${s} under serious: ${l}`);
    const half = lidOf(id, s, s, 30, 20, undefined, { serious: 0.5 });
    near(half[0], WANT[s][0] * 0.5, 1e-6, `${id} ${s} half serious`);
    near(half[1], WANT[s][1] * 0.5, 1e-6, `${id} ${s} half serious slope`);
  }
  for (const id of ANIMALS) for (let x = 0; x <= 3.4; x += 0.05) {
    const w = lidOf(id, "error", "standby", x, 120 + x, { past: asleep9 }, { serious: 1 });
    const n = lidOf(id, "standby", "idle", x, 140 + x, { past: awakeFrom("idle") }, { serious: 1 });
    assert.ok(w[0] === 0 && w[1] === 0 && n[0] === 0 && n[1] === 0, `${id} at ${x}: ${w} ${n}`);
  }
});

await check("calm and Still do not take the lid away at an approval or an error: it is the plain look asked for; it just arrives the same eased way", () => {
  for (const id of ANIMALS) for (const o of [{ calm: 1 }, { still: 1 }, { calm: 0.5, still: 0.5 }]) {
    for (const s of ["approval", "error", "banked", "standby"]) {
      const l = lidOf(id, s, s, 30, 20, undefined, o);
      near(l[0], WANT[s][0], 1e-6, `${id} ${s} ${JSON.stringify(o)}`);
    }
    let prev = null;
    for (let x = 0; x <= 3; x += FRAME) {
      const l = lidOf(id, "error", "idle", x, 50 + x, { prevAmp: 0 }, o, 0);
      if (prev) assert.ok(Math.abs(l[0] - prev[0]) < 0.006, `${id} ${JSON.stringify(o)}: jump at ${x}`);
      prev = l;
    }
    near(prev[0], 0.42, 0.003, `${id} ${JSON.stringify(o)}: error lid after 3 s`);
  }
});

await check("a blink still shuts the eye all the way with a lid on it (and the lid does not move with the blink)", () => {
  for (const id of ANIMALS) for (const s of ["approval", "error", "banked"]) {
    let lowest = 9, lidThen = null;
    for (let t = 0; t < 240; t += 0.02) {
      const u = C.species[id].uniforms(C.species[id].pose(s, s, 1e6, t, ampOf(s), {}, undefined, {}));
      if (u.uFace[0] < lowest) { lowest = u.uFace[0]; lidThen = u.uLid; }
    }
    assert.ok(lowest < 0.03, `${id} ${s}: the eye only closed to ${lowest} in four minutes`);
    near(lidThen[0], WANT[s][0], 1e-6, `${id} ${s}: the lid at the moment of a blink`);
  }
});

await check("hello and goodbye (switching faces) leave the lid exactly as it was", () => {
  for (const id of ANIMALS) for (const s of ["approval", "error", "banked", "standby", "idle"]) {
    for (const o of [{ goodbye: 0.3 }, { goodbye: 0.8 }, { hello: 0.2 }, { hello: 0.7 }]) {
      const l = lidOf(id, s, s, 30, 33, undefined, o);
      near(l[0], WANT[s][0], 1e-6, `${id} ${s} ${JSON.stringify(o)}`);
    }
  }
});

await check("the shader takes the lid: uLid and eyeLid are in the shared head (all five shaders), and only the four animals' eyes call it", () => {
  const gen = fs.readFileSync(path.join(SRC, "critters-gen.js"), "utf8");
  assert.equal((gen.match(/uniform float2 uLid;/g) || []).length, 5, "uLid is declared once in each shader (the shared head)");
  const defs = (gen.match(/float4 eyeLid\(/g) || []).length, calls = (gen.match(/eyeLid\(/g) || []).length - defs;
  assert.equal(defs, 5, "eyeLid is defined once in each shader");
  assert.equal(calls, 4, `the four animals' eyes call eyeLid (${calls}); the robot's do not`);
  assert.ok(!/uLid/.test(fs.readFileSync(path.join(SRC, "critter-robot.js"), "utf8")), "the robot's pose has no lid");
});

// ---- Part 2: the pixels (Playwright + the real shader) ---------------------------------
//
// The real shader of each animal (critters-gen.js, the desktop's copy) is drawn
// with the uniforms the pose gives (part 1's code), 512 px square, front on,
// and the pictures are compared pixel by pixel in the page. The clock the
// shader's orb swirls with is held at 0, so two draws of the same pose are the
// same picture.

let K;
try { K = await import("./uikit.mjs"); } catch { K = null; }
if (!K) {
  console.log("skip  the drawing checks: Playwright is not installed (tests/README.md)");
} else {
  const browser = await K.launch();
  const page = await browser.newPage();
  await page.setContent("<canvas id=c></canvas>");
  await page.addScriptTag({ content: fs.readFileSync(path.join(SRC, "critters-gen.js"), "utf8") });
  const COL = { idle: ["#7fe3ff", "#1d6f8a"], approval: ["#ffc14d", "#8a5a10"], standby: ["#9aa3ad", "#3a4048"],
    error: ["#ff5a7a", "#8a1f35"], banked: ["#b0b6bf", "#444a52"] };

  /** The uniforms of one animal in one state, settled and between blinks, with the lid as the pose gives it or as asked. */
  const pose = (id, state, lid) => {
    const a = C.species[id];
    const U = a.uniforms(a.pose(state, state, 30, 31.3, ampOf(state), {}, undefined, {}), null);
    if (lid) U.uLid = lid;
    return { state, U };
  };

  /** Draw the poses with the real shader and compare them; the numbers the checks need come back (no picture crosses to node). */
  const analyse = (id, poses, wanted) => page.evaluate(({ id, poses, COL, wanted }) => {
    const N = 512;
    const cv = document.getElementById("c"); cv.width = cv.height = N;
    const gl = cv.getContext("webgl2", { antialias: false, preserveDrawingBuffer: true });
    if (!gl) return { noGL: true };
    const VS = "#version 300 es\nvoid main(){ vec2 p = vec2((gl_VertexID << 1) & 2, gl_VertexID & 2); gl_Position = vec4(p * 2.0 - 1.0, 0.0, 1.0); }";
    const mk = (t, s) => { const sh = gl.createShader(t); gl.shaderSource(sh, s); gl.compileShader(sh);
      if (!gl.getShaderParameter(sh, gl.COMPILE_STATUS)) throw new Error(gl.getShaderInfoLog(sh)); return sh; };
    const pr = gl.createProgram(); gl.attachShader(pr, mk(gl.VERTEX_SHADER, VS)); gl.attachShader(pr, mk(gl.FRAGMENT_SHADER, window.JARVIS_CRITTERS[id]));
    gl.linkProgram(pr); if (!gl.getProgramParameter(pr, gl.LINK_STATUS)) throw new Error(gl.getProgramInfoLog(pr));
    const loc = {}; const n = gl.getProgramParameter(pr, gl.ACTIVE_UNIFORMS);
    for (let i = 0; i < n; i++) { const nm = gl.getActiveUniform(pr, i).name.replace(/\[0\]$/, ""); loc[nm] = gl.getUniformLocation(pr, nm); }
    const hex = (h) => [1, 3, 5].map((i) => parseInt(h.slice(i, i + 2), 16) / 255);
    const shots = poses.map((p) => {
      gl.useProgram(pr); gl.viewport(0, 0, N, N);
      for (const k in p.U) { const v = p.U[k], l = loc[k]; if (!l) continue;
        if (v.length === 1) gl.uniform1f(l, v[0]); else if (v.length === 2) gl.uniform2f(l, v[0], v[1]);
        else if (v.length === 3) gl.uniform3f(l, v[0], v[1], v[2]); else gl.uniform4f(l, v[0], v[1], v[2], v[3]); }
      const c = COL[p.state];
      gl.uniform3f(loc.uHot, ...hex(c[0])); gl.uniform3f(loc.uCool, ...hex(c[1])); gl.uniform3f(loc.uBg, 4 / 255, 7 / 255, 12 / 255);
      if (loc.uSeeThrough) gl.uniform1f(loc.uSeeThrough, 0);
      gl.uniform2f(loc.uRes, N, N);
      gl.uniform1f(loc.uYaw, 0); gl.uniform1f(loc.uPit, 0); gl.uniform1f(loc.uZoom, 1); gl.uniform1f(loc.uTime, 0);
      gl.uniform1f(loc.uPx, 2 / N); if (loc.uNoShadow) gl.uniform1f(loc.uNoShadow, 0);
      gl.drawArrays(gl.TRIANGLES, 0, 3);
      const out = new Uint8Array(N * N * 4); gl.readPixels(0, 0, N, N, gl.RGBA, gl.UNSIGNED_BYTE, out);
      return out;
    });
    const luma = (a, i) => 0.3 * a[i * 4] + 0.59 * a[i * 4 + 1] + 0.11 * a[i * 4 + 2];
    const diff = (a, b) => {
      let cnt = 0, x0 = 1e9, x1 = -1, y0 = 1e9, y1 = -1, left = 0;
      for (let i = 0; i < N * N; i++) {
        if (a[i * 4] !== b[i * 4] || a[i * 4 + 1] !== b[i * 4 + 1] || a[i * 4 + 2] !== b[i * 4 + 2]) {
          const x = i % N, y = (i / N) | 0;
          cnt++; if (x < x0) x0 = x; if (x > x1) x1 = x; if (y < y0) y0 = y; if (y > y1) y1 = y; if (x < N / 2) left++;
        }
      }
      return { cnt, x0, x1, y0, y1, left, right: cnt - left };
    };
    const ink = (a, box) => { let c = 0; for (let y = box.y0; y <= box.y1; y++) for (let x = box.x0; x <= box.x1; x++) if (luma(a, y * N + x) < 70) c++; return c; };
    const out = { N };
    // 0 idle as the pose draws it, 1 forced to no lid: must be the same picture.
    out.idle = diff(shots[0], shots[1]);
    // 5: a nearly shut lid; the box round what it changes is the eye, and the ink in it (lid off, 1) is the eye's dark.
    const big = diff(shots[1], shots[5]);
    out.big = big;
    const box = { x0: big.x0 - 1, x1: big.x1 + 1, y0: big.y0 - 1, y1: big.y1 + 1 + Math.round((big.y1 - big.y0) * 0.25) };
    out.box = box;
    out.inkOff = ink(shots[1], box);
    out.cover = [2, 3, 4, 5].map((i) => 1 - ink(shots[i], box) / out.inkOff);
    out.slope = [diff(shots[3], shots[6]).cnt, diff(shots[3], shots[7]).cnt, diff(shots[6], shots[7]).cnt];
    out.states = [[8, 9], [10, 11], [12, 13]].map(([a, b]) => diff(shots[a], shots[b]));
    out.shut = [diff(shots[14], shots[15]).cnt, diff(shots[16], shots[17]).cnt];
    return out;
  }, { id, poses, COL, wanted });

  for (const id of ANIMALS) {
    const list = [
      pose(id, "idle"),                                    // 0  as the pose draws it (no lid)
      pose(id, "idle", [0, 0]),                            // 1  the lid forced to nothing
      pose(id, "idle", [0.2, 0]), pose(id, "idle", [0.42, 0]), pose(id, "idle", [0.55, 0]), pose(id, "idle", [0.9, 0]),   // 2..5
      pose(id, "idle", [0.42, 1]), pose(id, "idle", [0.42, -1]),                                                          // 6, 7
      pose(id, "error"), pose(id, "error", [0, 0]),                                                                       // 8, 9
      pose(id, "approval"), pose(id, "approval", [0, 0]),                                                                 // 10, 11
      pose(id, "banked"), pose(id, "banked", [0, 0]),                                                                     // 12, 13
      pose(id, "standby"), pose(id, "standby", [0, 0]),                                                                   // 14, 15
      pose(id, "error", [0.42, 1]), pose(id, "error", [0.42, 1]),                                                         // 16, 17 (below: the eyes shut by hand)
    ];
    // Asleep the pose has the eyes shut, and the lid must leave the shut eye's line alone; and a blink
    // (an error's eyes squashed to nothing) with the worried lid on it is the same picture as without it.
    list[16].U.uFace = [0, 0, list[16].U.uFace[2]]; list[17].U.uFace = [0, 0, list[17].U.uFace[2]]; list[17].U.uLid = [0, 0];
    const r = await analyse(id, list, null);
    if (process.env.LIDS_DEBUG) console.log(id, JSON.stringify(r));
    if (r.noGL) { console.log(`skip  ${id}: this browser has no WebGL`); continue; }
    await check(`${id}: idle is pixel for pixel what it was - a lid of nothing draws nothing`, () => {
      assert.equal(r.idle.cnt, 0, `${r.idle.cnt} pixels differ`);
    });
    await check(`${id}: a lid changes only the eyes - two clusters, one each side of the head, no bigger than an eye`, () => {
      const b = r.big;
      assert.ok(b.cnt > 150, `only ${b.cnt} pixels changed by a 0.9 lid`);
      // (The otter floats with its head turned: only its near eye is on view.)
      if (id !== "seaotter") assert.ok(b.left > 0.25 * b.cnt && b.right > 0.25 * b.cnt, `one-sided: ${b.left} left, ${b.right} right`);
      assert.ok(b.y1 - b.y0 < r.N * 0.10, `the change is ${b.y1 - b.y0} px tall - more than an eye`);
      assert.ok(b.x1 - b.x0 < r.N * 0.5, `the change is ${b.x1 - b.x0} px wide - more than two eyes`);
    });
    await check(`${id}: a level lid of 0.2, 0.42, 0.55, 0.9 covers about that much of the eye, more and more`, () => {
      assert.ok(r.inkOff > 300, `only ${r.inkOff} dark pixels in the eye box`);
      // The dark of a round eye grows faster than the lid's depth (a lid of 0.2 takes 14 percent of a
      // circle's area, 0.42 takes 40, 0.55 takes 56, 0.9 takes 95), and the drawn eyes are not circles:
      // measured here 0.09-0.12, 0.33-0.49, 0.53-0.80 and all of it. The bands catch a lid twice or half its size.
      const band = [[0.04, 0.26], [0.24, 0.60], [0.42, 0.86], [0.92, 1.01]];
      for (let k = 0; k < 4; k++) assert.ok(r.cover[k] >= band[k][0] && r.cover[k] <= band[k][1],
        `${id}: a ${[0.2, 0.42, 0.55, 0.9][k]} lid covers ${r.cover[k].toFixed(2)} of the eye (${r.inkOff} dark pixels); it should be ${band[k]}`);
      for (let k = 1; k < 4; k++) assert.ok(r.cover[k] > r.cover[k - 1] + 0.08, `${id}: the covering does not grow: ${r.cover.map((c) => c.toFixed(2))}`);
    });
    await check(`${id}: the slope tilts the lid - worried one way, the other way round, both unlike a level lid`, () => {
      assert.ok(r.slope[0] > 30 && r.slope[1] > 30 && r.slope[2] > 60, `slope changes only ${r.slope} pixels`);
    });
    await check(`${id}: a shut eye keeps its line - asleep, and in a blink, the lid gives way (nothing is rubbed out)`, () => {
      assert.equal(r.shut[0], 0, `asleep: ${r.shut[0]} pixels of the shut eyes changed by the lid`);
      assert.equal(r.shut[1], 0, `blinking under a worried lid: ${r.shut[1]} pixels changed by the lid`);
    });
    await check(`${id}: dozing, waiting on you and an error each draw their lid over the eyes, and only the eyes, the worried one most`, () => {
      const [err, app, doze] = r.states;
      assert.ok(err.cnt > 100 && app.cnt > 40 && doze.cnt > 20, `lidded pixels: error ${err.cnt}, waiting ${app.cnt}, dozing ${doze.cnt}`);
      for (const [d, name] of [[err, "error"], [app, "waiting on you"], [doze, "dozing"]]) {
        assert.ok(d.y1 - d.y0 < r.N * 0.10 && d.x1 - d.x0 < r.N * 0.5, `${name}: the change is bigger than the eyes (${d.x1 - d.x0} x ${d.y1 - d.y0})`);
        if (id !== "seaotter") assert.ok(d.left > 0.25 * d.cnt && d.right > 0.25 * d.cnt, `${name}: one-sided (${d.left} / ${d.right})`);
      }
      assert.ok(err.cnt > app.cnt, `an error's lid (${err.cnt}) should cover more than the waiting one (${app.cnt})`);
    });
  }
  await browser.close();
}

if (fails.length) { console.log(`\n${fails.length} failed: ${fails.join("; ")}`); process.exit(1); }
console.log("\nall passed");
