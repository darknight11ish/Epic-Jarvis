/**
 * The faces' GPU watchdog, the animals' dimming and fallback, and the
 * "Jarvis isn't connected" ring - the fixes of 2026-09-28.
 *
 * The watchdog tests hand `GPU.poll` made-up measurements rather than
 * relying on how fast this machine's software GL happens to be today: what
 * they check is the RULE (three slow frames, one very slow one, a stall, a
 * quiet spell after a resize, a retry after a minute), which timing noise
 * would otherwise make flaky. How the real numbers came out is written in
 * docs/CRITTERS.md.
 */
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";
import * as K from "./uikit.mjs";

const HERE = dirname(fileURLToPath(import.meta.url));
const read = (p) => readFileSync(join(HERE, "..", p), "utf8");

// FACES_ROOT: serve another copy of src/ (say, with known-good pose files).
const { base, close } = await K.serve(process.env.FACES_ROOT || undefined);
const browser = await K.launch();
const fails = [];
const check = async (name, fn) => {
  try { await fn(); console.log(`ok    ${name}`); }
  catch (e) { fails.push(name); console.log(`FAIL  ${name}\n      ${e.message}`); }
};

/** The editor page (a plain browser preview: it needs nothing from the
 *  shell) with its own loop stopped, so a test drives every frame. `prep`
 *  runs before the page loads. */
async function editor(prep) {
  const page = await browser.newPage({ viewport: { width: 900, height: 700 } });
  if (prep) await prep(page);
  // Generous: twenty faces start drawing on load, and a busy machine with a
  // software GL can take well over the default 30 s (seen here once).
  await page.goto(`${base}/faces.html`, { timeout: 90000 });
  await page.waitForFunction(() => typeof drawSurface === "function" && typeof GPU !== "undefined", null, { timeout: 90000 });
  // Stop the page's own loop (and its start-up probe, which starts it
  // later): the next frame it schedules is this no-op, and that is the end.
  await page.evaluate(() => { frame = function () {}; });
  await page.waitForTimeout(1500);
  return page;
}

/** A fresh surface for face `id`, sized, out of its quiet spell. With
 *  `still`, the face draws nothing at all (so this machine's own speed never
 *  enters a test of the rule) - only the made-up card numbers do. */
const SURFACE = (id, still) => {
  const cv = document.createElement("canvas");
  cv.style.width = "240px"; cv.style.height = "240px";
  document.body.appendChild(cv);
  const s = makeSurface(THEME[id], cv, null);
  sizeSurface(s);
  // One frame first, so a shader build (and its quiet spell) is behind us.
  drawSurface(s, 1 / 30, "idle");
  s.quietUntil = 0; s.gpuSlow = 0;
  if (still) {
    const th = Object.create(THEME[id]);
    th.draw = () => {};
    s.theme = th;
  }
  return s;
};

/* ── The watchdog ────────────────────────────────────────────────────────── */

await check("a card that is slow sends a face flat in three frames, though the script is fast", async () => {
  const page = await editor();
  const got = await page.evaluate((SRC) => {
    const s = (0, eval)(SRC)("nucleus", true);
    const realPoll = GPU.poll;
    // The card reports four times its budget for every frame; the script
    // itself takes under a millisecond, which is all the old check saw.
    GPU.poll = (tok) => tok === s ? [{ at: performance.now() - 1, ms: gpuLimitMs() * 4 }] : [];
    const out = [];
    for (let i = 0; i < 5 && s.gpuOk !== false; i++) {
      const t0 = performance.now();
      drawSurface(s, 1 / 30, "idle");
      out.push({ ok: s.gpuOk, js: performance.now() - t0 });
    }
    GPU.poll = realPoll;
    return { frames: out.length, ok: s.gpuOk, trips: s.gpuTrips,
             retryIn: s.gpuRetryAt - performance.now() };
  }, SURFACE.toString());
  await page.close();
  assert.equal(got.ok, false, "never went flat");
  assert.equal(got.frames, 3, `took ${got.frames} frames`);
  assert.equal(got.trips, 1);
  assert.ok(got.retryIn > 55000 && got.retryIn <= 60000, `retry in ${got.retryIn} ms, not a minute`);
});

await check("one frame ten times too slow is enough", async () => {
  const page = await editor();
  const got = await page.evaluate((SRC) => {
    const s = (0, eval)(SRC)("redpanda", true);
    GPU.poll = (tok) => tok === s ? [{ at: performance.now() - 1, ms: gpuLimitMs() * 11, late: true }] : [];
    drawSurface(s, 1 / 30, "idle");
    return s.gpuOk;
  }, SURFACE.toString());
  await page.close();
  assert.equal(got, false);
});

await check("work from just after a resize or a build does not count", async () => {
  // Thirty resizes used to flip the otter flat for good.
  const page = await editor();
  const got = await page.evaluate((SRC) => {
    const s = (0, eval)(SRC)("seaotter", true);
    GPU.poll = (tok) => tok === s ? [{ at: performance.now() - 1, ms: gpuLimitMs() * 4 }] : [];
    let flips = 0;
    for (let i = 0; i < 30; i++) {
      s.canvas.style.width = (200 + (i % 2) * 40) + "px";
      sizeSurface(s);                       // a real change: a quiet spell starts
      drawSurface(s, 1 / 30, "idle");
      if (s.gpuOk === false) flips++;
    }
    return { flips, ok: s.gpuOk };
  }, SURFACE.toString());
  await page.close();
  assert.deepEqual(got, { flips: 0, ok: true });
});

await check("fast frames from the card take a strike back; a fast script does not", async () => {
  const page = await editor();
  const got = await page.evaluate((SRC) => {
    const s = (0, eval)(SRC)("nucleus", true);
    let ms = gpuLimitMs() * 4;
    GPU.poll = (tok) => tok === s ? [{ at: performance.now() - 1, ms }] : [];
    drawSurface(s, 1 / 30, "idle"); drawSurface(s, 1 / 30, "idle");
    const two = s.gpuSlow;
    ms = 2;                                  // the card keeps up again
    drawSurface(s, 1 / 30, "idle");
    const back = s.gpuSlow;
    GPU.poll = () => [];                     // the card says nothing
    for (let i = 0; i < 5; i++) drawSurface(s, 1 / 30, "idle");
    return { two, back, after: s.gpuSlow, ok: s.gpuOk };
  }, SURFACE.toString());
  await page.close();
  assert.deepEqual(got, { two: 2, back: 1, after: 1, ok: true });
});

await check("a flat face tries the card again after a minute, then two", async () => {
  const page = await editor();
  const got = await page.evaluate((SRC) => {
    const s = (0, eval)(SRC)("nucleus");
    gpuTrip(s, performance.now());
    const first = s.gpuRetryAt - performance.now();
    s.gpuRetryAt = performance.now() - 1;     // the minute is up
    GPU.poll = () => [];
    drawSurface(s, 1 / 30, "idle");
    const back = s.gpuOk;
    gpuTrip(s, performance.now());
    const second = s.gpuRetryAt - performance.now();
    return { first, back, second, trips: s.gpuTrips };
  }, SURFACE.toString());
  await page.close();
  assert.equal(got.back, true, "the retry did not give the card back");
  assert.ok(got.first > 59000 && got.first <= 60000, `first wait ${got.first}`);
  assert.ok(got.second > 119000 && got.second <= 120000, `second wait ${got.second}`);
  assert.equal(got.trips, 2);
});

await check("a page that gets no frames at all sends a slow face flat", async () => {
  // Measured: the 1200-pixel panda under a software driver got no frame for
  // fourteen seconds while the page's timers ran. Only a timer can see that.
  const page = await editor();
  const got = await page.evaluate((SRC) => new Promise((done) => {
    const s = (0, eval)(SRC)("redpanda");
    const other = (0, eval)(SRC)("nucleus");
    s.gpuSlow = 1; s.gpuAt = performance.now(); GPU_FACES.add(s);
    // A face that was keeping up is left alone by the same stall.
    other.gpuSlow = 0; other.gpuMs = 1; other.gpuAt = performance.now(); GPU_FACES.add(other);
    FRAME_AT = performance.now();
    setTimeout(() => done({ slow: s.gpuOk, fine: other.gpuOk }), GPU_STALL_MS + 700);
  }), SURFACE.toString());
  await page.close();
  assert.deepEqual(got, { slow: false, fine: true });
});

await check("a new face on the widget starts with a clean slate", async () => {
  const page = await K.open(browser, base, "floating.html", {}, { width: 240, height: 240 });
  const frame = await faceFrame(page);
  await frame.evaluate(() => {
    const real = drawSurface;
    drawSurface = function (s) { window.__s = s; return real.apply(this, arguments); };
  });
  await page.waitForTimeout(300);
  await frame.evaluate(() => { __s.gpuOk = false; __s.gpuTrips = 3; __s.gpuRetryAt = performance.now() + 9e5; });
  await page.evaluate(() => document.getElementById("face-frame").contentWindow.postMessage(
    { type: "jarvis-hud-face", state: "idle", appearance: { face: "pygmyowl", bindings: {} } }, location.origin));
  await page.waitForTimeout(300);
  const got = await frame.evaluate(() => ({ face: __s.theme.id, ok: __s.gpuOk, trips: __s.gpuTrips }));
  await page.close();
  assert.deepEqual(got, { face: "pygmyowl", ok: true, trips: 0 });
});

await check("a shader still building is not waited for: the face draws its fallback meanwhile", async () => {
  // KHR_parallel_shader_compile, faked: this machine's GL does not have it,
  // Windows' usually does. The panda's build froze the page for 246 ms.
  const page = await editor((p) => p.addInitScript(() => {
    const C = 0x91B1, ext = { COMPLETION_STATUS_KHR: C };
    const P = WebGL2RenderingContext.prototype;
    const getExt = P.getExtension, getProg = P.getProgramParameter;
    const asked = new WeakMap();
    window.__statusAsked = 0;
    P.getExtension = function (n) { return n === "KHR_parallel_shader_compile" ? ext : getExt.call(this, n); };
    P.getProgramParameter = function (pr, pname) {
      if (pname === C) {                     // "still building" three times per program
        const n = (asked.get(pr) || 0) + 1; asked.set(pr, n);
        return n > 3;
      }
      return getProg.call(this, pr, pname);
    };
    const getShader = P.getShaderParameter;
    P.getShaderParameter = function (sh, pname) {
      if (pname === this.COMPILE_STATUS) window.__statusAsked++;
      return getShader.call(this, sh, pname);
    };
  }));
  const got = await page.evaluate(() => {
    if (GPU.dead) return null;
    const FS = GLSL_COMMON + "void main(){ oCol = vec4(1.0, 0.0, 0.0, 1.0); }";
    const out = [];
    for (let i = 0; i < 5; i++) {
      const before = window.__statusAsked;
      const cv = GPU.pass("watchdog-test", FS, 8, 8, () => {});
      out.push({ drawn: Boolean(cv), statusRead: window.__statusAsked > before });
    }
    return { parallel: GPU.parallel, out };
  });
  await page.close();
  if (got === null) { console.log("      (skipped: no WebGL in this browser)"); return; }
  assert.equal(got.parallel, true);
  // Not drawn, and no status read (the read is what blocks), while building;
  // then read once and drawn.
  assert.deepEqual(got.out.map((o) => o.drawn), [false, false, false, true, true], JSON.stringify(got.out));
  assert.deepEqual(got.out.map((o) => o.statusRead), [false, false, false, true, false], JSON.stringify(got.out));
});

await check("the orb's clock handed to the shader stays small, and wraps without a jump", async () => {
  const page = await editor();
  const got = await page.evaluate(() => {
    const seen = [];
    const realPass = GPU.pass;
    GPU.pass = (key, fs, w, h, set) => {
      const L = new Proxy({}, { get: (_, k) => k });
      const G = new Proxy({}, { get: (_, k) => (...a) => { if (k === "uniform1f" && a[0] === "uTime") seen.push(a[1]); } });
      set(G, L);
      return document.createElement("canvas");
    };
    if (GPU.dead) return null;
    const th = THEME.redpanda, P = th.pose(0, "idle", 0);
    if (!P) return "no pose";
    const out = [];
    for (const phase of [5e6, CRITTER_TIME_WRAP * 3 - 1e-3, CRITTER_TIME_WRAP * 3 + 1e-3]) {
      PHASE = phase; GPUOK = true;
      th.gpu(document.createElement("canvas").getContext("2d"), 64, 64, 0, "idle", 0, P);
      out.push({ phase, u: seen[seen.length - 1] });
    }
    GPU.pass = realPass;
    const swirl = (u) => Math.sin(u * 1.3);
    return { wrap: CRITTER_TIME_WRAP, out, jump: Math.abs(swirl(out[1].u) - swirl(out[2].u)),
             same: Math.abs(swirl(out[0].u) - swirl(5e6)) };
  });
  await page.close();
  if (got === null) { console.log("      (skipped: no WebGL in this browser)"); return; }
  assert.notEqual(got, "no pose", "critter-pose.js did not load, so the panda has no pose to draw");
  for (const o of got.out) assert.ok(Math.abs(o.u) < got.wrap, `uTime ${o.u} for PHASE ${o.phase}`);
  assert.ok(got.jump < 0.01, `the swirl jumps by ${got.jump} at the wrap`);
  assert.ok(got.same < 1e-6, `the swirl moved by ${got.same}`);
});

/* ── The animals ─────────────────────────────────────────────────────────── */

await check("standby and banked dim the whole animal, as much as they dim other faces", async () => {
  const page = await editor();
  const got = await page.evaluate((SRC) => {
    const lin = (c) => { c /= 255; return c <= 0.04045 ? c / 12.92 : Math.pow((c + 0.055) / 1.055, 2.4); };
    const out = {};
    for (const id of ["redpanda", "pygmyowl", "seaotter", "monkey", "robot", "arc"]) {
      out[id] = {};
      for (const st of ["idle", "standby", "banked"]) {
        const s = (0, eval)(SRC)(id);
        s.gpuOk = false; sizeSurface(s);     // the flat drawing: the same on any machine
        // Five seconds on the pose's clock: standby's dim follows the animal
        // nodding off (sleepDim), which takes about three.
        const realNow = performance.now, t0 = realNow.call(performance);
        let fake = t0;
        performance.now = () => fake;
        for (let i = 0; i < 150; i++) { fake += 1000 / 30; drawSurface(s, 1 / 30, st); }
        performance.now = realNow;
        const d = s.ctx.getImageData(0, 0, s.w, s.h).data;
        let sum = 0;
        for (let i = 0; i < d.length; i += 4) sum += 0.2126 * lin(d[i]) + 0.7152 * lin(d[i + 1]) + 0.0722 * lin(d[i + 2]);
        out[id][st] = sum / (d.length / 4);
        s.canvas.remove();
      }
      out[id] = { standby: +(out[id].standby / out[id].idle).toFixed(2), banked: +(out[id].banked / out[id].idle).toFixed(2) };
    }
    return out;
  }, SURFACE.toString());
  await page.close();
  console.log("      standby/idle, banked/idle:", JSON.stringify(got));
  for (const id of ["redpanda", "pygmyowl", "seaotter", "monkey", "robot"]) {
    assert.ok(got[id].standby < 0.6, `${id} standby is ${got[id].standby} of idle`);
    assert.ok(got[id].banked < got[id].standby, `${id} banked is not dimmer than standby`);
  }
});

await check("the animal's orb is not dimmed twice", async () => {
  // The whole picture is dimmed once (FACE_DIM); the colours handed to it
  // must be the state's own, not already dimmed as other faces' are.
  const page = await editor();
  const got = await page.evaluate((SRC) => {
    const s = (0, eval)(SRC)("redpanda");
    s.gpuOk = false; sizeSurface(s);
    let hot = null;
    const th = THEME.redpanda, real = th.flat;
    th.flat = function (g, w, h, st) { hot = this.st[st].hot; return real.apply(this, arguments); };
    // Five seconds on the pose's clock: standby's dim follows the animal
    // nodding off (sleepDim), which takes about three.
    const realNow = performance.now;
    let fake = realNow.call(performance);
    performance.now = () => fake;
    for (let i = 0; i < 150; i++) { fake += 1000 / 30; drawSurface(s, 1 / 30, "standby"); }
    performance.now = realNow;
    th.flat = real;
    return { hot, colour: s.colShown.a, dim: FACE_DIM };
  }, SURFACE.toString());
  await page.close();
  assert.equal(got.hot, got.colour, "the animal was handed a different colour from the state's");
  assert.equal(got.dim, 0.6);
});

await check("an animal whose pose script failed still draws, still and neutral", async () => {
  const page = await editor((p) => p.route(/critter-(pose|owl|otter|monkey|robot)\.js$/, (r) => r.abort()));
  const got = await page.evaluate((SRC) => {
    const out = {};
    for (const id of ["redpanda", "pygmyowl", "seaotter", "monkey", "robot"]) {
      const s = (0, eval)(SRC)(id);
      drawSurface(s, 1 / 30, "idle");
      const d = s.ctx.getImageData(0, 0, s.w, s.h).data;
      let lit = 0;
      for (let i = 0; i < d.length; i += 4) if (d[i] + d[i + 1] + d[i + 2] > 90) lit++;
      out[id] = { species: THEME[id].species === null, lit: lit / (d.length / 4) };
    }
    return out;
  }, SURFACE.toString());
  await page.close();
  for (const [id, r] of Object.entries(got)) {
    assert.ok(r.species, `${id}'s pose script was meant to be missing`);
    assert.ok(r.lit > 0.05, `${id} drew ${(r.lit * 100).toFixed(1)}% of its square`);
  }
});

/* ── "Jarvis isn't connected", and banked's notches ──────────────────────── */

const LIVE = { connected: true, stale: false, base: "x", last_id: 9, power: "active",
  power_set_by: null, activity: "idle", approvals: 0, error: null,
  attention: { known: true, limit: 4, remaining: 4, spent: 0, muted: false, blocked_by: null,
               pending: 0, banked: false, digest_hour: 18, digest_due: false } };

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
/** Brightness at the ring's radius, and just outside the face's own edge. */
const RING = () => {
  const cv = document.getElementById("display-canvas");
  const g = cv.getContext("2d"), w = cv.width, side = Math.min(cv.width, cv.height);
  const at = (r) => {
    let sum = 0;
    for (let k = 0; k < 64; k++) {
      const a = (k / 64) * Math.PI * 2;
      const d = g.getImageData(Math.round(w / 2 + Math.cos(a) * side * r), Math.round(cv.height / 2 + Math.sin(a) * side * r), 1, 1).data;
      sum += d[0] + d[1] + d[2];
    }
    return sum / 64;
  };
  return { ring: at(0.4532), outside: at(0.485) };
};

await check("the floating face: no approval pose on a stale link, then standby with a ring", async () => {
  const page = await K.open(browser, base, "floating.html", {}, { width: 240, height: 240 });
  const frame = await faceFrame(page);
  const state = async () => frame.evaluate(() => ({ st: LIVE_STATE, off: LIVE_OFFLINE,
    label: document.getElementById("display-canvas").getAttribute("aria-label") }));
  const status = () => page.locator("#face-status").textContent();

  await page.evaluate((l) => window.__emit("jarvis-link", { ...l, approvals: 2 }), LIVE);
  await page.waitForTimeout(250);
  const live = await state();

  // The stream drops. Approve is blocked at once, so the face stops waving
  // for a decision at once - rule 4 - but the ring waits out the 12 s grace.
  await page.evaluate((l) => window.__emit("jarvis-link",
    { ...l, approvals: 2, connected: false, stale: true, activity: "speaking", error: "stream closed" }), LIVE);
  await page.waitForTimeout(250);
  const stale = await state();
  const staleStatus = await status();

  await page.waitForTimeout(12300);
  const offline = await state();
  const offlineStatus = await status();
  const ringOn = await frame.evaluate(RING);

  await page.evaluate((l) => window.__emit("jarvis-link", l), LIVE);
  await page.waitForTimeout(500);
  const back = await state();
  const backStatus = await status();
  const ringOff = await frame.evaluate(RING);
  await page.close();

  assert.deepEqual(live, { st: "approval", off: false, label: "Jarvis's face: approval" });
  assert.notEqual(stale.st, "approval", "an approval face on a stale link");
  assert.equal(stale.off, false, "the ring came before the grace was up");
  assert.equal(staleStatus, "");
  assert.deepEqual(offline, { st: "standby", off: true, label: "Jarvis isn't connected" });
  assert.equal(offlineStatus, "Jarvis isn't connected");
  assert.ok(ringOn.ring > ringOn.outside + 20, `no ring: ${JSON.stringify(ringOn)}`);
  assert.deepEqual(back, { st: "idle", off: false, label: "Jarvis's face: idle" });
  assert.equal(backStatus, "");
  assert.ok(ringOff.ring < ringOff.outside + 8, `the ring stayed: ${JSON.stringify(ringOff)}`);
});

await check("banked shows its notches on the desktop: the waiting count reaches the face", async () => {
  const page = await K.open(browser, base, "floating.html", {}, { width: 240, height: 240 });
  const frame = await faceFrame(page);
  await page.evaluate((l) => window.__emit("jarvis-link",
    { ...l, attention: { ...l.attention, remaining: 0, pending: 3, banked: true } }), LIVE);
  await page.waitForTimeout(700);
  const got = await frame.evaluate(() => ({ st: LIVE_STATE, waiting: HUD.waiting }));
  await page.close();
  assert.deepEqual(got, { st: "banked", waiting: 3 });
});

await check("the widget sends the face the same signal as the floating face", () => {
  const widget = read("src/widget.js"), floating = read("src/floating.js");
  assert.match(widget, /type: "jarvis-hud-face", \.\.\.faceSignal\(currentLink\(\)\)/);
  assert.match(floating, /faceSignal\(currentLink\(\)\)/);
  assert.doesNotMatch(widget + floating, /surfaceState\(currentLink\(\)\)/, "a face fed surfaceState alone has no ring");
});

await check("faceSignal and surfaceState: the rules in one place", async () => {
  const L = await import("../src/jarvis-link.js");
  const live = { connected: true, stale: false, activity: "speaking", approvals: 1, power: "active",
                 attention: { pending: 2, banked: false } };
  const down = { ...live, connected: false, stale: true };
  assert.equal(L.OFFLINE_GRACE_MS, 12000, "the phone's grace is 12 s");
  assert.deepEqual(L.faceSignal(live), { state: "approval", offline: false, waiting: 2, serious: false });
  // A link object that is not the window's own has no history: down is offline.
  assert.deepEqual(L.faceSignal(down), { state: "standby", offline: true, waiting: 2, serious: false });
  assert.equal(L.surfaceState({ ...live, stale: true }), "standby");
  assert.equal(L.surfaceState(live), "approval");
});

/* ── The two still rings: not connected, and error (owner, 2026-09-29) ───── */

const RING_FIXTURE = JSON.parse(read("tests/fixtures/ring-cases.json"));
const GROUND = [4, 7, 12];   // faces.html BG, #04070c

/** Pixels of a face's surface, read at 3, 6, 9 and 12 o'clock (and the gap's edges)
 *  of the ring radius. The face itself draws nothing, so only the rings are seen. */
const RING_PROBE = ([SRC, id, state, offline, size]) => {
  const s = (0, eval)(SRC)(id, true);
  const cv = s.ctx.canvas;
  cv.style.width = size + "px"; cv.style.height = size + "px";
  sizeSurface(s);
  s.offline = offline;
  for (let i = 0; i < 6; i++) drawSurface(s, 1 / 30, state);
  const w = s.w, h = s.h, side = Math.min(w, h), R = side * 0.44 * 1.03;
  const px = (deg, r) => {
    const a = deg * Math.PI / 180;
    const d = s.ctx.getImageData(Math.round(w / 2 + Math.cos(a) * r), Math.round(h / 2 + Math.sin(a) * r), 1, 1).data;
    return [d[0], d[1], d[2]];
  };
  // How many pixels across the ring is, along the 3 o'clock row.
  let thick = 0;
  for (let dx = -8; dx <= 8; dx++) {
    const d = s.ctx.getImageData(Math.round(w / 2 + R) + dx, Math.round(h / 2), 1, 1).data;
    if (Math.abs(d[0] - 4) + Math.abs(d[1] - 7) + Math.abs(d[2] - 12) > 40) thick++;
  }
  // Around the whole ring: which of 72 five-degree steps are lit.
  const lit = [];
  for (let k = 0; k < 72; k++) {
    const c = px(k * 5, R);
    lit.push(Math.abs(c[0] - 4) + Math.abs(c[1] - 7) + Math.abs(c[2] - 12) > 40 ? 1 : 0);
  }
  return { right: px(0, R), bottom: px(90, R), left: px(180, R), top: px(270, R),
           bottomLeft: px(90 + 45, R), bottomRight: px(90 - 45, R), thick, lit, w };
};
const contrastOf = (rgb) => {
  const f = (v) => { v /= 255; return v <= 0.03928 ? v / 12.92 : Math.pow((v + 0.055) / 1.055, 2.4); };
  const L = (c) => 0.2126 * f(c[0]) + 0.7152 * f(c[1]) + 0.0722 * f(c[2]);
  const a = L(rgb), b = L(GROUND);
  return (Math.max(a, b) + 0.05) / (Math.min(a, b) + 0.05);
};

await check("the ring colours match the golden fixture both apps are held to, and stay 3.2:1 or more", async () => {
  const page = await editor();
  const got = await page.evaluate((cases) => cases.map((c) => ({ tone: ringTone(c.c, c.bg), k: ringContrast(ringTone(c.c, c.bg), c.bg) })),
    RING_FIXTURE.cases);
  await page.close();
  RING_FIXTURE.cases.forEach((c, i) => {
    assert.deepEqual(got[i].tone, c.tone, `${c.colour} on ${c.ground}`);
    assert.ok(got[i].k >= 3.2 && got[i].k <= 5.6, `${c.colour} on ${c.ground} measures ${got[i].k.toFixed(2)}:1`);
  });
  assert.ok(RING_FIXTURE.cases.length >= 50);
});

await check("the not-connected ring is a complete circle that stands out from the ground (3:1 or more, it was 1.65:1)", async () => {
  const page = await editor();
  const got = await page.evaluate(RING_PROBE, [SURFACE.toString(), "redpanda", "standby", true, 300]);
  await page.close();
  for (const at of ["right", "bottom", "left", "top", "bottomLeft", "bottomRight"]) {
    const k = contrastOf(got[at]);
    assert.ok(k >= 3, `the ring at ${at} measures ${k.toFixed(2)}:1 against the ground (${got[at]})`);
  }
  assert.ok(got.lit.every((v) => v === 1), "the not-connected ring has a gap: " + got.lit.join(""));
});

await check("the error ring: a thin arc with a gap at the bottom, on every character face, and on nothing else", async () => {
  const page = await editor();
  const per = {};
  for (const id of ["redpanda", "pygmyowl", "seaotter", "monkey", "robot"]) {
    per[id] = await page.evaluate(RING_PROBE, [SURFACE.toString(), id, "error", false, 300]);
  }
  const notCharacter = await page.evaluate(RING_PROBE, [SURFACE.toString(), "arc", "error", false, 300]);
  const idle = await page.evaluate(RING_PROBE, [SURFACE.toString(), "redpanda", "idle", false, 300]);
  const waiting = await page.evaluate(RING_PROBE, [SURFACE.toString(), "redpanda", "approval", false, 300]);
  const offline = await page.evaluate(RING_PROBE, [SURFACE.toString(), "redpanda", "standby", true, 300]);
  await page.close();
  for (const [id, r] of Object.entries(per)) {
    for (const at of ["right", "left", "top", "bottomLeft", "bottomRight"]) {
      assert.ok(contrastOf(r[at]) >= 3, `${id}: the error ring at ${at} measures ${contrastOf(r[at]).toFixed(2)}:1`);
    }
    // The gap is at the bottom: the ground shows at six o'clock...
    assert.ok(contrastOf(r.bottom) < 1.3, `${id}: no gap at the bottom (${r.bottom})`);
    // ...and it is 70 degrees wide (14 of the 72 five-degree steps, centred on step 18), not more, not less.
    const dark = r.lit.map((v, i) => (v ? -1 : i)).filter((i) => i >= 0);
    assert.ok(dark.length >= 12 && dark.length <= 16, `${id}: the gap is ${dark.length * 5} degrees wide`);
    assert.ok(dark.every((i) => i >= 10 && i <= 26), `${id}: the gap is not at the bottom: ${dark}`);
    // The colour is the error colour (rose), not the standby grey.
    assert.ok(r.right[0] > r.right[2] + 30, `${id}: the error ring is not rose: ${r.right}`);
  }
  // Thin: clearly thinner than the not-connected ring, which is the heavy one.
  assert.ok(per.redpanda.thick <= offline.thick - 1, `error ${per.redpanda.thick}px vs not-connected ${offline.thick}px`);
  assert.ok(offline.thick >= 3, `the not-connected ring is ${offline.thick}px at 300`);
  // Not a character face, not another state, not while not connected: no error ring.
  assert.ok(notCharacter.lit.every((v) => v === 0), "the Arc face got an error ring");
  assert.ok(idle.lit.every((v) => v === 0), "an idle face has a ring");
  assert.ok(waiting.lit.slice(0, 72).filter((v) => v).length < 30, "the waiting clock was mistaken for a ring");
  assert.ok(offline.lit.every((v) => v === 1), "the offline ring lost its closed shape");
});

await check("the error ring does not move: the same pixels a second later, and under Still", async () => {
  const page = await editor();
  const a = await page.evaluate(RING_PROBE, [SURFACE.toString(), "monkey", "error", false, 200]);
  const b = await page.evaluate(([SRC, size]) => {
    const s = (0, eval)(SRC)("monkey", true);
    s.ctx.canvas.style.width = size + "px"; s.ctx.canvas.style.height = size + "px";
    sizeSurface(s);
    for (let i = 0; i < 90; i++) drawSurface(s, 1 / 30, "error");
    const w = s.w, h = s.h, R = Math.min(w, h) * 0.44 * 1.03;
    const first = [];
    for (let k = 0; k < 72; k++) {
      const an = k * 5 * Math.PI / 180;
      first.push(Array.from(s.ctx.getImageData(Math.round(w / 2 + Math.cos(an) * R), Math.round(h / 2 + Math.sin(an) * R), 1, 1).data));
    }
    for (let i = 0; i < 90; i++) drawSurface(s, 1 / 30, "error");
    let same = 0;
    for (let k = 0; k < 72; k++) {
      const an = k * 5 * Math.PI / 180;
      const d = Array.from(s.ctx.getImageData(Math.round(w / 2 + Math.cos(an) * R), Math.round(h / 2 + Math.sin(an) * R), 1, 1).data);
      if (d.join() === first[k].join()) same++;
    }
    return same;
  }, [SURFACE.toString(), 200]);
  await page.close();
  assert.ok(a.lit.some((v) => v === 1));
  assert.equal(b, 72, "the error ring changed between two moments: it pulses or moves");
  // Static by construction: the source draws it with no clock and no alpha.
  const src = read("src/faces.html");
  const fn = src.slice(src.indexOf("function drawErrorRing("), src.indexOf("function drawSurface("));
  assert.doesNotMatch(fn, /s\.clock|fxAge|performance\.now|globalAlpha|Math\.sin/, "the error ring reads a clock or fades");
});

/* ── A focus session is not a sleeping animal (owner, 2026-09-29) ────────── */

await check("a focus session's Quiet shows the focus buddy (idle); a hand-set Quiet, or any standby, stays asleep", async () => {
  const L = await import("../src/jarvis-link.js");
  const rest = { connected: true, stale: false, activity: "idle", approvals: 0, power: "active",
                 attention: { pending: 0, banked: false } };
  // The bug: this said "standby" (Quiet is asleep), so the animal slept through its own focus session.
  assert.equal(L.surfaceState({ ...rest, power: "quiet", powerSetBy: "focus" }), "idle");
  assert.equal(L.faceSignal({ ...rest, power: "quiet", powerSetBy: "focus" }).state, "idle");
  assert.equal(L.restingAsleep({ ...rest, power: "quiet", powerSetBy: "focus" }), false);
  // Control: everything else that was asleep still is.
  assert.equal(L.surfaceState({ ...rest, power: "quiet", powerSetBy: "override" }), "standby", "a Quiet set by hand");
  assert.equal(L.surfaceState({ ...rest, power: "quiet", powerSetBy: null }), "standby");
  assert.equal(L.surfaceState({ ...rest, power: "quiet", powerSetBy: "schedule" }), "standby");
  assert.equal(L.surfaceState({ ...rest, power: "standby", powerSetBy: "focus" }), "standby", "only Quiet is the session's");
  assert.equal(L.surfaceState({ ...rest, power: "standby", powerSetBy: "override" }), "standby");
  assert.equal(L.surfaceState({ ...rest, power: "active", powerSetBy: "focus" }), "idle");
  // Not connected is asleep whatever the reason (the stream keeps the last power).
  assert.equal(L.surfaceState({ ...rest, connected: false, stale: true, power: "quiet", powerSetBy: "focus" }), "standby");
  // Busy still wins over resting, as before.
  assert.equal(L.surfaceState({ ...rest, activity: "speaking", power: "quiet", powerSetBy: "focus" }), "speaking");
});

await check("the floating face shows idle for a focus session's Quiet and standby for a hand-set one", async () => {
  const page = await K.open(browser, base, "floating.html", {}, { width: 240, height: 240 });
  const frame = await faceFrame(page);
  const state = () => frame.evaluate(() => LIVE_STATE);
  await page.evaluate((l) => window.__emit("jarvis-link", { ...l, power: "quiet", power_set_by: "focus" }), LIVE);
  await page.waitForTimeout(300);
  const focus = await state();
  await page.evaluate((l) => window.__emit("jarvis-link", { ...l, power: "quiet", power_set_by: "override" }), LIVE);
  await page.waitForTimeout(300);
  const byHand = await state();
  await page.close();
  assert.equal(focus, "idle", "the animal slept through a focus session");
  assert.equal(byHand, "standby", "a Quiet set by hand must stay asleep");
});

await check("faces.html's own specState (its fallback port of the tray rule) agrees", async () => {
  const page = await editor();
  const got = await page.evaluate(() => {
    const base = { connected: true, stale: false, activity: "idle", approvals: 0, attention: { banked: false } };
    return [
      specState({ ...base, power: "quiet", powerSetBy: "focus" }),
      specState({ ...base, power: "quiet", powerSetBy: "override" }),
      specState({ ...base, power: "standby", powerSetBy: "focus" }),
    ];
  });
  await page.close();
  assert.deepEqual(got, ["idle", "standby", "standby"]);
});

await browser.close();
close();
if (fails.length) { console.log(`\n${fails.length} failed`); process.exit(1); }
console.log("\nall face-watchdog checks passed");
