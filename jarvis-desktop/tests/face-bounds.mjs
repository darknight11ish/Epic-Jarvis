/**
 * The animals' bounding volumes never cut an animal off (2026-09-29).
 *
 * Each animal's shader ray-marches a signed distance field, and to save the
 * graphics card work it first asks which stretch of each ray could be inside
 * the animal at all (`animalSpan` in the animal's .sksl, joined from a sphere
 * round each part; a ray that meets none is not marched). A sphere that is
 * too small would quietly cut a hand, an ear or a tail off - in one pose,
 * from one side - and nobody would notice until it happened on screen.
 *
 * So this draws a spread of poses from four sides with the real shader and
 * again with the same shader minus the tight volumes (`animalSpan` replaced
 * by the single outer sphere every animal had before), and compares the two
 * pictures pixel by pixel. A ray that meets the animal takes exactly the
 * steps it always took, so the pictures should be the same except for a
 * stray pixel or two along an edge, where a ray that only skims past the
 * animal can go either way. The measured worst is 10 pixels in one 96-pixel
 * picture (docs/CRITTERS.md, "The bounding volumes").
 *
 * The poses: every state, looks in all directions and the mouth's shapes, the
 * idle happenings and cute moments (the robot's zip, the monkey's swing, the
 * owl's turns, the otter's roll), talking gestures, hello and goodbye when
 * switching faces, waking and falling asleep, petting, and the focus stretch.
 *
 * CONTROL: the same comparison with every sphere shrunk to half does show the
 * difference - so a pass means something.
 *
 *     node tests/face-bounds.mjs
 *
 * Needs Playwright and a browser with WebGL (software WebGL is fine); the pose
 * half is pure node and always runs.
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
const ANIMALS = ["redpanda", "pygmyowl", "seaotter", "monkey", "robot"];
const STATES = ["idle", "listening", "thinking", "speaking", "approval", "standby", "error", "banked"];

const fails = [];
const check = async (name, fn) => {
  try { await fn(); console.log(`ok    ${name}`); }
  catch (e) { fails.push(name); console.log(`FAIL  ${name}\n      ${e.message}`); }
};

/** A spread of poses for one animal: [{ U: uniforms, state }]. */
function poses(id) {
  const api = C.species[id];
  const out = [];
  const add = (state, t, opts = {}, since = 30, prev = state, hist, amp = 0.3, look = {}, mouth) => {
    const P = api.pose(state, prev, since, t, amp, look, hist, opts);
    out.push({ state, U: api.uniforms(P, mouth) });
  };
  // Every state at a few moments, looking every way, with the mouth's shapes.
  const looks = [{}, { x: 1, y: 1, w: 1 }, { x: -1, y: -1, w: 1 }, { x: 1, y: -1, w: 1 }];
  const mouths = [undefined, { open: 1, wide: 0, round: 0 }, { open: 0.5, wide: 1, round: 0 }, { open: 0.7, wide: 0, round: 1 }];
  STATES.forEach((s, i) => {
    add(s, 3.7 + i * 5.3, { variety: 1 }, 30, s, undefined, s === "speaking" ? 0.5 : 0.1, looks[i % 4], mouths[i % 4]);
    add(s, 41.9 + i, {}, 30, s, undefined, 0.2, looks[(i + 1) % 4], mouths[(i + 2) % 4]);
  });
  // The idle happenings and cute moments, spread over the animal's whole timeline.
  const busy = [];
  for (let t = 0; t < 4096; t += 0.25) if (api.busy("idle", t)) busy.push(t);
  for (let i = 0; i < 24; i++) add("idle", busy[Math.floor((i * busy.length) / 24)], { cute_moments: 1, variety: 1 }, 1e6, "idle", undefined, 0);
  // Talking gestures and phrase ends.
  const gest = [];
  for (let t = 0; t < 4096; t += 0.25) if (api.gesturing(t)) gest.push(t);
  for (let i = 0; i < 10; i++) add("speaking", gest[Math.floor((i * gest.length) / 10)], { variety: 1 }, 30, "speaking", undefined, 0.5, {}, mouths[i % 4]);
  // Hello and goodbye, part way, in states that play them.
  for (const s of ["idle", "listening", "speaking", "standby"]) {
    for (const f of [0.15, 0.4, 0.65, 0.9]) {
      add(s, 30, { hello: f });
      add(s, 30, { goodbye: f });
    }
  }
  // Waking up and falling asleep, part way.
  const asleep = [{ state: "standby", gap: 9, amp: 0 }, { state: "idle", gap: 20, amp: 0 }];
  const awake = [{ state: "idle", gap: 20, amp: 0 }, { state: "standby", gap: 9, amp: 0 }];
  for (const x of [0.3, 0.9, 1.5, 2.1]) add("idle", 120 + x, {}, x, "standby", { past: asleep }, 0);
  for (const x of [0.5, 1.3, 2.1, 2.9]) add("standby", 140 + x, {}, x, "idle", { past: awake }, 0);
  // Petting (both ways), the focus stretch, a fact's nod and the glow.
  for (const px of [-1, 0, 1]) add("idle", 30 + px, { pet: 1, petX: px, petDir: px || 1 });
  add("idle", 30, { focusEnd: 1.2 });
  add("idle", 30, { ackNod: 0.4, ackGlow: 0.9 });
  return out;
}

const ALL = Object.fromEntries(ANIMALS.map((id) => [id, poses(id)]));

await check("the pose sweep is a real one: dozens of different poses for every animal", async () => {
  for (const id of ANIMALS) {
    assert.ok(ALL[id].length >= 90, `${id}: only ${ALL[id].length} poses`);
    const distinct = new Set(ALL[id].map((p) => JSON.stringify(p.U, (k, v) => (typeof v === "number" ? Math.round(v * 1000) / 1000 : v))));
    assert.ok(distinct.size >= 70, `${id}: only ${distinct.size} of them differ`);
  }
});

await check("every animal's shader asks animalSpan and joins its parts' spheres to the outer one", async () => {
  const gen = fs.readFileSync(path.join(SRC, "critters-gen.js"), "utf8");
  assert.equal((gen.match(/float2 span = animalSpan\(ro, rd\);/g) || []).length, ANIMALS.length);
  assert.equal((gen.match(/return clipSpan\(ro, rd, s, CAM_TARGET, BOUND_R\);/g) || []).length, ANIMALS.length);
});

let K;
try { K = await import("./uikit.mjs"); } catch { K = null; }
if (!K) {
  console.log("skip  the drawing checks: Playwright is not installed (tests/README.md)");
} else {
  const browser = await K.launch();
  const page = await browser.newPage();
  await page.setContent("<canvas id=c></canvas>");
  await page.addScriptTag({ content: fs.readFileSync(path.join(SRC, "critters-gen.js"), "utf8") });
  const COL = { idle: ["#7fe3ff", "#1d6f8a"], listening: ["#ff8a3d", "#8a3a12"], thinking: ["#8f7bff", "#3a3490"],
    speaking: ["#9ff0ff", "#2a7890"], approval: ["#ffc14d", "#8a5a10"], standby: ["#9aa3ad", "#3a4048"],
    error: ["#ff5a7a", "#8a1f35"], banked: ["#b0b6bf", "#444a52"] };

  /** Draw every pose with the real shader and a reference; count the pixels that differ. */
  const compare = (id, variant) => page.evaluate(({ id, poses, COL, variant }) => {
    const N = 96;
    const cv = document.getElementById("c"); cv.width = cv.height = N;
    const gl = cv.getContext("webgl2", { antialias: false, preserveDrawingBuffer: true });
    if (!gl) return { noGL: true };
    const real = window.JARVIS_CRITTERS[id];
    const swap = (from, to) => {
      if (!real.includes(from)) throw new Error(`the shader no longer contains: ${from}`);
      return real.replace(from, to);
    };
    // The reference is the shader as it was: one sphere round the target.
    const ref = swap("float2 span = animalSpan(ro, rd);", "float2 span = sphereSpan(ro, rd, CAM_TARGET, BOUND_R);");
    // The control draws with every part's sphere half the size.
    const test = variant === "half" ? swap("return joinSpan(s, sphereSpan(ro, rd, c, r));", "return joinSpan(s, sphereSpan(ro, rd, c, r * 0.5));") : real;
    const VS = "#version 300 es\nvoid main(){ vec2 p = vec2((gl_VertexID << 1) & 2, gl_VertexID & 2); gl_Position = vec4(p * 2.0 - 1.0, 0.0, 1.0); }";
    const build = (fs_) => {
      const mk = (t, s) => { const sh = gl.createShader(t); gl.shaderSource(sh, s); gl.compileShader(sh);
        if (!gl.getShaderParameter(sh, gl.COMPILE_STATUS)) throw new Error(gl.getShaderInfoLog(sh)); return sh; };
      const pr = gl.createProgram(); gl.attachShader(pr, mk(gl.VERTEX_SHADER, VS)); gl.attachShader(pr, mk(gl.FRAGMENT_SHADER, fs_));
      gl.linkProgram(pr); if (!gl.getProgramParameter(pr, gl.LINK_STATUS)) throw new Error(gl.getProgramInfoLog(pr));
      const loc = {}; const n = gl.getProgramParameter(pr, gl.ACTIVE_UNIFORMS);
      for (let i = 0; i < n; i++) { const nm = gl.getActiveUniform(pr, i).name.replace(/\[0\]$/, ""); loc[nm] = gl.getUniformLocation(pr, nm); }
      return { pr, loc };
    };
    const hex = (h) => [1, 3, 5].map((i) => parseInt(h.slice(i, i + 2), 16) / 255);
    const draw = (prog, p, view, out) => {
      const { pr, loc } = prog; gl.useProgram(pr); gl.viewport(0, 0, N, N);
      for (const k in p.U) { const v = p.U[k], l = loc[k]; if (!l) continue;
        if (v.length === 1) gl.uniform1f(l, v[0]); else if (v.length === 2) gl.uniform2f(l, v[0], v[1]);
        else if (v.length === 3) gl.uniform3f(l, v[0], v[1], v[2]); else gl.uniform4f(l, v[0], v[1], v[2], v[3]); }
      const c = COL[p.state];
      gl.uniform3f(loc.uHot, ...hex(c[0])); gl.uniform3f(loc.uCool, ...hex(c[1])); gl.uniform3f(loc.uBg, 4 / 255, 7 / 255, 12 / 255);
      if (loc.uSeeThrough) gl.uniform1f(loc.uSeeThrough, 0);
      gl.uniform2f(loc.uRes, N, N);
      gl.uniform1f(loc.uYaw, view[0]); gl.uniform1f(loc.uPit, view[1]); gl.uniform1f(loc.uZoom, view[2]); gl.uniform1f(loc.uTime, 0);
      gl.uniform1f(loc.uPx, 2 / N); if (loc.uNoShadow) gl.uniform1f(loc.uNoShadow, 0);
      gl.drawArrays(gl.TRIANGLES, 0, 3); gl.readPixels(0, 0, N, N, gl.RGBA, gl.UNSIGNED_BYTE, out);
    };
    const A = build(ref), B = build(test);
    // Four sides: front, a three-quarter turn, from above, and from behind.
    const VIEWS = [[0, 0, 1], [0.6, 0.3, 0.8], [0, 1.2, 0.6], [3.14, -0.3, 0.7]];
    const a = new Uint8Array(N * N * 4), b = new Uint8Array(N * N * 4);
    let total = 0, worst = 0, images = 0, largest = 0;
    for (let i = 0; i < poses.length; i++) {
      for (const view of [VIEWS[0], VIEWS[1 + (i % 3)]]) {
        draw(A, poses[i], view, a); draw(B, poses[i], view, b);
        let n = 0;
        for (let j = 0; j < a.length; j += 4) {
          const d = Math.max(Math.abs(a[j] - b[j]), Math.abs(a[j + 1] - b[j + 1]), Math.abs(a[j + 2] - b[j + 2]));
          if (d > 8) n++;
          if (d > largest) largest = d;
        }
        total += n; worst = Math.max(worst, n); images++;
      }
    }
    return { images, total, worst, largest };
  }, { id, poses: ALL[id], COL, variant });

  for (const id of ANIMALS) {
    await check(`${id}: the tight volumes draw the same picture as the single sphere, from four sides`, async () => {
      const r = await compare(id, "real");
      if (r.noGL) { console.log("      (skipped: this browser has no WebGL)"); return; }
      console.log(`      ${r.images} pictures at 96 px: ${r.total} pixels differ (most in one picture: ${r.worst}; largest step ${r.largest}/255)`);
      // Measured here: at most 3 in one picture, and under one in three pictures on average.
      assert.ok(r.worst <= 8, `${id}: ${r.worst} pixels differ in one picture - a part is being cut off`);
      assert.ok(r.total <= r.images * 0.7, `${id}: ${r.total} pixels differ over ${r.images} pictures`);
    });
  }

  await check("CONTROL: with every part's sphere shrunk to half the test does see a cut-off animal", async () => {
    const r = await compare("redpanda", "half");
    if (r.noGL) { console.log("      (skipped: this browser has no WebGL)"); return; }
    console.log(`      ${r.images} pictures: ${r.total} pixels differ (most in one: ${r.worst})`);
    assert.ok(r.worst > 8 && r.total > r.images * 5, "shrunken spheres cut the panda off, and the check did not notice");
  });

  await browser.close();
}

console.log(fails.length ? `\n${fails.length} failed: ${fails.join(", ")}` : "\nno animal is cut off by its bounding volumes");
process.exit(fails.length ? 1 : 0);
