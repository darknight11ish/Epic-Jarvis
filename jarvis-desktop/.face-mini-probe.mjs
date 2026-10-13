/**
 * Scratch probe (not committed): does a ray-marched animal face read at the
 * quickbar reactor's size? Renders the real shader at several pixel sizes and
 * writes PNGs plus a few numbers.
 */
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { createRequire } from "node:module";

const HERE = path.dirname(fileURLToPath(import.meta.url));
const SRC = path.join(HERE, "src");
const require = createRequire(import.meta.url);
for (const f of ["critter-pose.js", "critter-owl.js", "critter-otter.js", "critter-monkey.js", "critter-robot.js"])
  require(path.join(SRC, f));

const K = await import("./tests/uikit.mjs");
const browser = await K.launch();
const page = await browser.newPage();
await page.setContent("<canvas id=c></canvas>");
for (const f of ["critter-pose.js", "critter-owl.js", "critter-otter.js", "critter-monkey.js", "critter-robot.js"]) {
  await page.addScriptTag({ content: fs.readFileSync(path.join(SRC, f), "utf8") });
}
await page.addScriptTag({ content: fs.readFileSync(path.join(SRC, "critters-gen.js"), "utf8") });

const COL = { idle: ["#7fe3ff", "#1d6f8a"], listening: ["#ff8a3d", "#8a3a12"],
  thinking: ["#8f7bff", "#3a3490"], speaking: ["#9ff0ff", "#2a7890"],
  approval: ["#ffc14d", "#8a5a10"], standby: ["#9aa3ad", "#3a4048"],
  error: ["#ff5a7a", "#8a1f35"], banked: ["#b0b6bf", "#444a52"] };

const outDir = path.join(HERE, ".face-mini-out");
fs.mkdirSync(outDir, { recursive: true });

const SIZES = [232, 120, 96, 68, 40, 34];

const result = await page.evaluate(async ({ SRC, COL, SIZES }) => {
  const mod = await import("file:///" + SRC.replace(/\\/g, "/") + "/critter-pose.js").catch(() => null);
  // critter-pose is a classic script; it may already be on window via the page.
  return null;
}, { SRC, COL, SIZES });

// Render with the real shader, sized as the app sizes it: trace at max(96, w),
// then draw down into w pixels with high-quality smoothing.
const shots = await page.evaluate(({ COL, SIZES, IDS, STATES }) => {
  const cv = document.getElementById("c");
  const gl = cv.getContext("webgl2", { antialias: false, preserveDrawingBuffer: false });
  const VS = "#version 300 es\nvoid main(){ vec2 p = vec2((gl_VertexID << 1) & 2, gl_VertexID & 2); gl_Position = vec4(p * 2.0 - 1.0, 0.0, 1.0); }";
  const mk = (t, s) => { const sh = gl.createShader(t); gl.shaderSource(sh, s); gl.compileShader(sh); return sh; };
  const build = (fs_) => {
    const pr = gl.createProgram();
    gl.attachShader(pr, mk(gl.VERTEX_SHADER, VS));
    gl.attachShader(pr, mk(gl.FRAGMENT_SHADER, fs_));
    gl.linkProgram(pr);
    const loc = {}; const n = gl.getProgramParameter(pr, gl.ACTIVE_UNIFORMS);
    for (let i = 0; i < n; i++) { const nm = gl.getActiveUniform(pr, i).name.replace(/\[0\]$/, ""); loc[nm] = gl.getUniformLocation(pr, nm); }
    return { pr, loc };
  };
  const hex = (h) => [1, 3, 5].map((i) => parseInt(h.slice(i, i + 2), 16) / 255);
  const progs = {};
  for (const id of IDS) progs[id] = build(window.JARVIS_CRITTERS[id]);
  const out = {};
  for (const id of IDS) {
    const api = window.CritterPose.species[id];
    const shotsFor = {};
    for (const state of STATES) {
      const P = api.pose(state, state, 30, 8.4, state === "speaking" ? 0.6 : 0.12, { x: 0, y: 0, w: 0 }, { past: [] }, {});
      const U = api.uniforms(P, state === "speaking" ? { open: 0.6, wide: 0.3, round: 0.1 } : null);
      const per = {};
      for (const W of SIZES) {
        const trace = Math.max(96, W);        // FacePace.tracePx's own floor
        const { pr, loc } = progs[id];
        gl.useProgram(pr);
        gl.viewport(0, 0, trace, trace);
        for (const k in U) { const v = U[k], l = loc[k]; if (!l) continue;
          if (v.length === 1) gl.uniform1f(l, v[0]); else if (v.length === 2) gl.uniform2f(l, v[0], v[1]);
          else if (v.length === 3) gl.uniform3f(l, v[0], v[1], v[2]); else gl.uniform4f(l, v[0], v[1], v[2], v[3]); }
        const c = COL[state];
        gl.uniform3f(loc.uHot, ...hex(c[0])); gl.uniform3f(loc.uCool, ...hex(c[1]));
        gl.uniform3f(loc.uBg, 4 / 255, 7 / 255, 12 / 255);
        if (loc.uSeeThrough) gl.uniform1f(loc.uSeeThrough, 0);
        gl.uniform2f(loc.uRes, trace, trace);
        gl.uniform1f(loc.uYaw, 0); gl.uniform1f(loc.uPit, 0); gl.uniform1f(loc.uZoom, 1); gl.uniform1f(loc.uTime, 0);
        gl.uniform1f(loc.uPx, 2 / trace);
        if (loc.uNoShadow) gl.uniform1f(loc.uNoShadow, W < 150 ? 1 : 0);
        gl.drawArrays(gl.TRIANGLES, 0, 3);
        // Read the traced picture back, then scale it to W exactly as the app
        // does (imageSmoothingQuality high).
        const big = new Uint8Array(trace * trace * 4);
        gl.readPixels(0, 0, trace, trace, gl.RGBA, gl.UNSIGNED_BYTE, big);
        const c2 = document.createElement("canvas");
        c2.width = c2.height = trace;
        const g2 = c2.getContext("2d");
        const img = g2.createImageData(trace, trace);
        // readPixels is bottom-up; flip while copying.
        for (let y = 0; y < trace; y++) {
          const src = (trace - 1 - y) * trace * 4, dst = y * trace * 4;
          img.data.set(big.subarray(src, src + trace * 4), dst);
        }
        g2.putImageData(img, 0, 0);
        const c3 = document.createElement("canvas");
        c3.width = c3.height = W;
        const g3 = c3.getContext("2d");
        g3.imageSmoothingEnabled = true; g3.imageSmoothingQuality = "high";
        g3.drawImage(c2, 0, 0, W, W);
        per[W] = c3.toDataURL("image/png");
      }
      shotsFor[state] = per;
    }
    out[id] = shotsFor;
  }
  return out;
}, { COL, SIZES, IDS: ["redpanda", "pygmyowl", "seaotter", "monkey", "robot"],
     STATES: ["idle", "listening", "thinking", "speaking", "approval", "standby", "error"] });

for (const [id, states] of Object.entries(shots)) {
  for (const [state, per] of Object.entries(states)) {
    for (const [w, url] of Object.entries(per)) {
      fs.writeFileSync(path.join(outDir, `${id}-${state}-${w}.png`),
        Buffer.from(String(url).split(",")[1], "base64"));
    }
  }
}
console.log("wrote", outDir);
await browser.close();
