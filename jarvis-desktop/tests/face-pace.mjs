/**
 * The animals' resolution and frame-rate choices - the owner's "sharp
 * animals on capable hardware" (2026-09-28).
 *
 * The rules are in face-pace.js (pure, run here under node against the
 * spec's own numbers); the words in face-tuning.js (and the phone's
 * FaceBudget.kt, held to the same spec by its SpecDriftTest). Then, in the
 * real pages: an animal at Maximum is traced at 2x2, a small one skips its
 * shadow, the widget's face now rests (it drew every frame in every state),
 * a picked 60 lifts an animal's rest to 60, the Faces window starts an
 * animal at High and says how it is running, and Settings offers the six
 * frame rates and a cost line per level.
 */
import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import vm from "node:vm";
import { createRequire } from "node:module";
import { fileURLToPath } from "node:url";

const HERE = path.dirname(fileURLToPath(import.meta.url));
const SRC = path.join(HERE, "..", "src");
const SPEC = JSON.parse(fs.readFileSync(path.join(SRC, "jarvis-visual-spec.json"), "utf8"));
const PHONE_SPEC = JSON.parse(fs.readFileSync(path.join(HERE, "..", "..", "jarvis-client", "app", "src", "test",
  "resources", "jarvis-visual-spec.json"), "utf8"));

// face-pace.js reads the spec from JARVIS_SPEC, as it does in the page.
globalThis.JARVIS_SPEC = SPEC;
const require = createRequire(import.meta.url);
const P = require("../src/face-pace.js");
const tuning = await import("../src/face-tuning.js");

const fails = [];
const check = async (name, fn) => {
  try { await fn(); console.log(`ok    ${name}`); }
  catch (e) { fails.push(name); console.log(`FAIL  ${name}\n      ${e.message}`); }
};

/* ── The rules ────────────────────────────────────────────────────────────── */

await check("both copies of the spec carry the same animal rules", async () => {
  assert.deepEqual(PHONE_SPEC.frame_rate.animals, SPEC.frame_rate.animals);
  assert.deepEqual(PHONE_SPEC.frame_rate.pick_rule, SPEC.frame_rate.pick_rule);
  assert.deepEqual(PHONE_SPEC.frame_rate.targets, SPEC.frame_rate.targets);
  assert.deepEqual(SPEC.frame_rate.targets, ["auto", "30", "60", "90", "120", "max"]);
});

await check("one set of words: the spec, Settings and the Faces window agree", async () => {
  const levels = SPEC.frame_rate.animals.levels;
  assert.deepEqual(levels.map((l) => l.id), ["low", "medium", "high", "max"], "stored ids changed: saved settings would break");
  assert.deepEqual(levels.map((l) => l.label), ["Lower", "Balanced", "High", "Maximum"]);
  assert.deepEqual(tuning.QUALITIES.map((q) => [q.id, q.label, q.note]), levels.map((l) => [l.id, l.label, l.note]));
  assert.deepEqual(P.LEVELS.map((l) => l.label), levels.map((l) => l.label));
  assert.ok(!levels.some((l) => /battery saver/i.test(l.label)), "the phone already has a Battery saver switch");
  assert.deepEqual(tuning.FRAME_RATES.map((f) => f.id), SPEC.frame_rate.targets);
  for (const l of levels) assert.ok(l.note.length < 110, `${l.label}'s note is not one plain line`);
  assert.match(tuning.FRAME_RATE_NOTE, /on a 144 Hz screen 90 draws 144/);
  assert.doesNotMatch(tuning.FRAME_RATE_NOTE, /becomes 72/, "the note still has the old round-to-nearest example");
});

await check("the animal scales: desktop 0.62 / 0.8 / 1 / 2x2, phone 0.4 / 0.5 / 0.75 / 1", async () => {
  assert.deepEqual(P.LEVELS.map((l) => l.desktop_scale), [0.62, 0.8, 1.0, 1.0]);
  assert.deepEqual(P.LEVELS.map((l) => l.desktop_supersample), [1, 1, 1, 2]);
  assert.deepEqual(P.LEVELS.map((l) => l.phone_trace), [0.4, 0.5, 0.75, 1.0]);
  const html = fs.readFileSync(path.join(SRC, "faces.html"), "utf8");
  // faces.html's TIERS carries the same numbers (gpu is the scale).
  for (const l of P.LEVELS) {
    const m = new RegExp(`${l.id}:\\s*\\{[^}]*gpu: ([0-9.]+)[^}]*shaderSS: (\\d)`).exec(html);
    assert.ok(m, `TIERS.${l.id} has no shaderSS`);
    assert.equal(+m[1], l.desktop_scale, `TIERS.${l.id}.gpu`);
    assert.equal(+m[2], l.desktop_supersample, `TIERS.${l.id}.shaderSS`);
  }
});

await check("traced pixels: High is the screen's own, Maximum 2x2 capped at 2400, Lower 62%", async () => {
  assert.equal(P.tracePx(600, 600, "high"), 600);
  assert.equal(P.tracePx(600, 600, "max"), 1200);
  assert.equal(P.tracePx(1800, 1800, "max"), 2400, "not capped");
  assert.equal(P.tracePx(600, Math.round(600 * 0.62), "low"), 372);
  assert.equal(P.tracePx(60, 60, "high"), 96, "under the 96 px floor");
  assert.equal(P.noShadow(180, "high"), true, "a small face kept its shadow");
  assert.equal(P.noShadow(600, "low"), true, "Lower kept its shadow");
  assert.equal(P.noShadow(600, "max"), false);
});

await check("the pick rule: whole shares of the screen, rounded up - never slower than the pick", async () => {
  const hzs = [60, 75, 90, 100, 120, 144, 165, 240];
  const fps = (t, hz) => hz / P.strideFor(t, hz);
  // The owner's decision of 2026-09-28: round UP.
  assert.equal(P.strideFor("120", 165), 1, "120 on 165 Hz draws 165, not 82.5");
  assert.equal(P.strideFor("90", 120), 1, "90 on 120 Hz draws 120, not 60");
  assert.equal(P.strideFor("90", 144), 1, "the note says 90 draws 144 on 144 Hz");
  assert.equal(P.strideFor("60", 144), 2, "60 on 144 Hz draws 72");
  assert.equal(P.strideFor("30", 144), 4, "30 on 144 Hz draws 36");
  assert.equal(P.strideFor("60", 60), 1);
  assert.equal(P.strideFor("120", 60), 1, "a pick above the screen's rate is every frame");
  assert.equal(fps("90", 90), 90);
  assert.equal(fps("60", 120), 60);
  assert.equal(fps("30", 60), 30);
  assert.equal(fps("30", 120), 30);
  assert.equal(fps("120", 144), 144);
  assert.equal(fps("auto", 165), 165);
  assert.equal(fps("max", 240), 240);
  // A screen reporting a hair under its nominal rate still halves evenly.
  assert.equal(P.strideNear(59.94, 30), 2);
  for (const hz of hzs) {
    for (const t of tuning.FRAME_RATES.map((f) => f.id)) {
      const s = P.strideFor(t, hz);
      assert.equal(tuning.strideFor(t, hz), s, `Settings and the face disagree on ${t} at ${hz} Hz`);
      const want = Math.min(Number(t) || hz, hz);
      assert.ok(hz / s >= want - 1e-9, `${t} at ${hz} Hz draws ${hz / s}, slower than the pick`);
      assert.ok(hz / (s + 1) < want, `${t} at ${hz} Hz: stride ${s + 1} would still reach the pick`);
    }
  }
});

await check("an animal's resting rate: Auto 60 with headroom, 30 without, full rate while a happening plays", async () => {
  assert.equal(P.restFps("idle", "auto", true, false), 60);
  assert.equal(P.restFps("idle", "auto", false, false), 30);
  assert.equal(P.restFps("idle", "auto", false, true), 0, "a happening is drawn at the full rate");
  assert.equal(P.restFps("approval", "auto", true, true), 60, "busy is for idle only");
  for (const t of ["30", "60", "90", "120"]) assert.equal(P.restFps("idle", t, false, false), +t, `picked ${t}`);
  assert.equal(P.restFps("approval", "90", false, false), 90);
  assert.equal(P.restFps("idle", "max", false, false), 0, "Max rests at the screen's rate");
  for (const t of ["auto", "30", "120", "max"]) {
    assert.equal(P.restFps("standby", t, true, true), 15, `standby under ${t}`);
    assert.equal(P.restFps("banked", t, true, true), 2, `banked under ${t}`);
    for (const st of ["listening", "thinking", "speaking", "error"]) assert.equal(P.restFps(st, t, false, false), 0);
  }
});

await check("headroom comes after ten frames under half a 60 fps frame, and goes above 0.8 of it", async () => {
  const h = P.makeHeadroom();
  for (let i = 0; i < 9; i++) h.frame(2);
  assert.equal(h.on, false, "decided on fewer than ten frames");
  h.frame(2);
  assert.equal(h.on, true);
  for (let i = 0; i < 6; i++) h.frame(12);       // avg climbs, but under 13.3
  assert.equal(h.on, true, "flapped inside the dead band");
  for (let i = 0; i < 60; i++) h.frame(20);
  assert.equal(h.on, false);
  for (let i = 0; i < 12; i++) h.frame(10);      // under 13.3 but not under 8.3
  assert.equal(h.on, false, "came back inside the dead band");
});

await check("Auto's ladder for an animal, on 60, 120 and 144 Hz screens", async () => {
  const show = (L) => L.map((r) => `${r.tier}@${r.stride}`).join(" ");
  assert.equal(show(P.ladder(60)), "max@1 high@1 medium@1 medium@2 low@2");
  assert.equal(show(P.ladder(120)), "max@1 high@1 high@2 medium@2 medium@4 low@4");
  assert.equal(show(P.ladder(144)), "max@1 high@1 high@2 medium@2 medium@4 low@4");
  // A picked 60 on 120 Hz: nothing goes under it.
  assert.equal(show(P.ladder(120, 2)), "max@2 high@2 medium@2 medium@4 low@4");
  const L = P.ladder(120);
  assert.equal(P.rungOf(L, "high", 1), 1);
  assert.equal(P.rungOf(L, "medium", 4), 4);
  assert.equal(P.rungOf(L, "low", 1), 5, "an unknown pairing lands no richer than it was");
});

await check("Auto steps down in the owner's order and climbs to Maximum only under a quarter of the budget", async () => {
  const L = P.ladder(120), holds = P.makeHolds();
  let i = 0, now = 0;
  const seen = [];
  while (i < L.length - 1) { i = P.decide(L, i, 2.0, "max", holds, now += 2000); seen.push(`${L[i].tier}@${L[i].stride}`); }
  assert.deepEqual(seen, ["high@1", "high@2", "medium@2", "medium@4", "low@4"]);
  assert.equal(P.decide(L, i, 5, "max", holds, now), i, "went below the last rung");
  // Cheap, but every rung just left is held for 10 s.
  assert.equal(P.decide(L, i, 0.1, "max", holds, now + 1000), i, "climbed straight back");
  now += 200000;
  const up = [];
  while (i > 0) { const j = P.decide(L, i, 0.1, "max", holds, now += 2000); if (j === i) break; i = j; up.push(L[i].tier); }
  assert.deepEqual(up, ["medium", "medium", "high", "high", "max"]);
  // From High at the full rate: 0.3 of the budget stays at High; 0.2 climbs.
  const h2 = P.makeHolds();
  assert.equal(P.decide(L, 1, 0.3, "max", h2, 0), 1, "climbed to Maximum at 30% of the budget");
  assert.equal(P.decide(L, 1, 0.2, "max", h2, 0), 0);
  assert.equal(P.decide(L, 1, 0.2, "high", h2, 0), 1, "climbed past the top it was given");
  // A frame-rate step back up needs 0.33, not 0.55.
  assert.equal(P.decide(L, 2, 0.4, "max", h2, 0), 2);
  assert.equal(P.decide(L, 2, 0.3, "max", h2, 0), 1);
});

await check("the readout says fps, ms per frame and the animal's resolution", async () => {
  assert.equal(P.readout(59.6, 4.24, { px: 1200, of: 600 }), "60 fps · 4.2 ms per frame · animal resolution 1200 px (200%)");
  assert.equal(P.readout(30, 12, null), "30 fps · 12.0 ms per frame");
});

await check("the pose files say when an idle happening plays, the same as the phone's fixture", async () => {
  const ctx = { console };
  ctx.globalThis = ctx; ctx.window = ctx;
  vm.createContext(ctx);
  for (const f of ["critter-pose.js", "critter-owl.js", "critter-otter.js", "critter-monkey.js", "critter-robot.js"]) {
    vm.runInContext(fs.readFileSync(path.join(SRC, f), "utf8"), ctx, { filename: f });
  }
  const C = ctx.CritterPose;
  assert.equal(C.HAPPENING_S, SPEC.frame_rate.animals.happening_s);
  const gold = JSON.parse(fs.readFileSync(path.join(HERE, "..", "..", "jarvis-client", "app", "src", "test",
    "resources", "critter-busy-golden.json"), "utf8"));
  for (const sp of ["redpanda", "pygmyowl", "seaotter", "monkey", "robot"]) {
    const got = gold.times.map((t) => (C.species[sp].busy("idle", t) ? "1" : "0")).join("");
    assert.equal(got, gold.busy[sp], `${sp}: run python3 tools/gen_critters.py`);
    const share = [...got].filter((c) => c === "1").length / got.length;
    assert.ok(share > 0.1 && share < 0.4, `${sp} is busy ${Math.round(share * 100)}% of idle time`);
  }
});

/* ── In the pages ─────────────────────────────────────────────────────────── */

let K;
try { K = await import("./uikit.mjs"); } catch (e) { K = null; }
if (K) {
  const { base, close } = await K.serve();
  const browser = await K.launch();

  /** A display-mode face with this computer's face settings. */
  async function display(face, tune, size = 300) {
    const t = await import("../src/face-tuning.js");
    const page = await K.open(browser, base, `faces.html?mode=display&face=${face}`, {}, { width: size, height: size });
    await page.evaluate(([key, value]) => localStorage.setItem(key, value),
      [t.FACE_TUNING_KEY, JSON.stringify({ ...t.FACE_TUNING_DEFAULT, ...tune })]);
    await page.reload();
    await page.waitForFunction(() => document.getElementById("display-canvas"), null, { timeout: 30000 });
    await page.waitForTimeout(1500);
    return page;
  }
  /** drawSurface calls a second, over 2 s. */
  const rate = (page) => page.evaluate(() => new Promise((done) => {
    let n = 0;
    const real = drawSurface;
    drawSurface = function (...a) { n++; return real.apply(this, a); };
    setTimeout(() => { drawSurface = real; done(n / 2); }, 2000);
  }));

  await check("an animal picked at Maximum is traced at 2x2 and averaged down", async () => {
    const page = await display("redpanda", { quality: "max", autoAdjust: false });
    await page.waitForFunction(() => VIEW && VIEW.trace, null, { timeout: 30000 });
    const got = await page.evaluate(() => ({ trace: VIEW.trace, gpupx: GPUPX, q: QNAME, ss: Q.shaderSS }));
    await page.close();
    assert.equal(got.q, "max");
    assert.equal(got.ss, 2);
    assert.equal(got.trace.px, Math.min(2400, 2 * Math.max(96, Math.min(got.trace.of, got.gpupx))));
    assert.equal(got.trace.px, 2 * got.trace.of, `traced ${got.trace.px} px for a ${got.trace.of} px face`);
  });

  await check("the widget's face rests now: idle at 30, standby at 15 (it drew every frame)", async () => {
    const page = await display("arc", { autoAdjust: false, frameRate: "auto" });
    const idle = await rate(page);
    await page.evaluate(() => { LIVE_STATE = "standby"; });
    await page.waitForTimeout(900);
    const standby = await rate(page);
    await page.evaluate(() => { LIVE_STATE = "thinking"; });
    await page.waitForTimeout(900);
    const busy = await rate(page);
    await page.close();
    assert.ok(idle > 20 && idle < 38, `idle drew ${idle} a second`);
    assert.ok(standby > 9 && standby < 19, `standby drew ${standby} a second`);
    assert.ok(busy > idle * 1.4, `thinking drew ${busy} a second against idle's ${idle}`);
  });

  await check("a picked 60 lifts an animal's rest to 60; standby stays 15", async () => {
    // Headless Chromium runs its frames at 60 Hz. The Lower level so the
    // software renderer keeps up; the pacing is what is measured.
    const page = await display("redpanda", { quality: "low", frameRate: "60", autoAdjust: false }, 160);
    await page.evaluate(() => { GPUOK = false; });
    const idle60 = await rate(page);
    await page.evaluate(() => { LIVE_STATE = "standby"; });
    await page.waitForTimeout(900);
    const standby = await rate(page);
    await page.close();
    assert.ok(standby > 9 && standby < 19, `standby drew ${standby} a second`);
    assert.ok(idle60 > standby * 2, `a picked 60 rested at ${idle60} a second`);
  });

  await check("the Faces window starts an animal at High and says how it is running", async () => {
    const page = await K.open(browser, base, "faces.html", {}, { width: 1300, height: 950 });
    await page.waitForTimeout(800);
    const before = await page.evaluate(() => QNAME);
    await page.evaluate(() => openSolo(THEME.redpanda));
    const q = await page.evaluate(() => QNAME);
    await page.waitForFunction(() => / fps · [0-9.]+ ms per frame/.test(document.getElementById("solo-read").textContent),
      null, { timeout: 30000 });
    const read = await page.evaluate(() => document.getElementById("solo-read").textContent);
    const chips = await page.locator("#fps .chip").allTextContents();
    const levels = await page.locator("#quality .chip").allTextContents();
    await page.evaluate(() => closeSolo());
    const after = await page.evaluate(() => QNAME);
    await page.close();
    assert.equal(before === "max", false);
    assert.ok(q === "high" || q === "max" || q === "medium" || q === "low", q);
    assert.match(read, /animal resolution \d+ px \(\d+%\)/, read);
    assert.deepEqual(chips, ["auto", "30", "60", "90", "120", "max"]);
    assert.deepEqual(levels, ["Lower", "Balanced", "High", "Maximum"]);
    assert.notEqual(after, "max", "the grid kept Maximum after the animal closed");
  });

  await check("Settings: six frame rates, a cost line per level, and 90 is saved", async () => {
    const page = await K.open(browser, base, "settings.html", {}, { width: 760, height: 1400 });
    await page.locator("#face-tuning > summary").click();
    const rates = await page.locator("#face-fps .choice").allTextContents();
    assert.deepEqual(rates, ["Auto", "30", "60", "90", "120", "Max"]);
    const q = await page.locator("#face-quality .choice").allTextContents();
    assert.deepEqual(q, ["Lower", "Balanced", "High", "Maximum"]);
    const notes = await page.locator("#face-quality-levels li").allTextContents();
    assert.equal(notes.length, 4);
    assert.match(notes[3], /^Maximum - The sharpest edges/);
    assert.match(await page.locator("#face-fps-note").textContent(), /90 draws 144/);
    await page.locator('#face-fps .choice[data-value="90"]').click();
    const saved = await page.evaluate(() => JSON.parse(localStorage.getItem("jarvis.faceTuning")));
    assert.equal(saved.frameRate, "90");
    assert.equal(saved.autoAdjust, false);
    assert.deepEqual(page.__errors, []);
    await page.close();
  });

  await browser.close();
  close();
} else {
  console.log("skip  the page checks: Playwright is not installed (tests/README.md)");
}

console.log(fails.length ? `\n${fails.length} failed: ${fails.join(", ")}` : "\nthe animals' quality and pacing hold");
process.exit(fails.length ? 1 : 0);
