/**
 * The animals' sleeping Zs, "Keep the animal still" and the serious moment
 * on every desktop surface - the owner's decisions of 2026-09-28.
 *
 *  - Zs rise over a sleeping animal on standby, never while Jarvis cannot be
 *    reached (the hollow ring alone says that), and are gone when it wakes.
 *    They come from the pose's own point beside the head, so they follow it.
 *  - "Keep the animal still" is saved on this computer, reaches every face
 *    page (read at start and on Settings' save), eases the pose's `still` in,
 *    and changes nothing on a face that is not an animal.
 *  - A crisis answer's `wellbeing` event reaches the Widget's and the
 *    floating face's frames through jarvis-link.js, and the HUD's.
 *
 * The numbers the Zs are drawn from are the pose code's (CritterPose.zs) and
 * are checked against the phone's copy by the phone's CritterPoseTest.
 */
import assert from "node:assert/strict";
import * as K from "./uikit.mjs";

const { base, close } = await K.serve();
const browser = await K.launch();
const fails = [];
const check = async (name, fn) => {
  try { await fn(); console.log(`ok    ${name}`); }
  catch (e) { fails.push(name); console.log(`FAIL  ${name}\n      ${e.message}`); }
};

const LIVE = { connected: true, stale: false, base: "x", last_id: 9, power: "active",
  power_set_by: null, activity: "idle", approvals: 0, error: null,
  attention: { known: true, limit: 4, remaining: 4, spent: 0, muted: false, blocked_by: null,
               pending: 0, banked: false, digest_hour: 18, digest_due: false } };
const PANDA = { face: "redpanda", bindings: {}, updated: 0, source: "server", shared: true };

async function faceFrame(page) {
  const deadline = Date.now() + 15000;
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

/** The brightest pixel where the Zs rise (up and out from their point),
 *  leaving out a band round the offline ring's radius. */
const ZS_REGION = () => {
  const z = window.__faceZs;
  const cv = document.getElementById("display-canvas");
  const g = cv.getContext("2d"), W = cv.width, H = cv.height, k = Math.min(W, H) / 2;
  const side = z.x >= 0 ? 1 : -1;
  let best = 0;
  for (let u = 0; u <= 0.40; u += 0.01) {
    for (let v = 0.0; v <= 0.34; v += 0.01) {
      const x = z.x + side * u, y = z.y + v;
      const px = Math.round(W / 2 + x * k), py = Math.round(H / 2 - y * k);
      if (px < 0 || py < 0 || px >= W || py >= H) continue;
      const r = Math.hypot(px - W / 2, py - H / 2) / Math.min(W, H);
      if (Math.abs(r - 0.4532) < 0.02) continue;
      const d = g.getImageData(px, py, 1, 1).data;
      best = Math.max(best, d[0] + d[1] + d[2]);
    }
  }
  return best;
};

await check("Zs rise over a sleeping animal on standby, never while not connected, and go when it wakes", async () => {
  const page = await K.open(browser, base, "floating.html", { appearance: PANDA }, { width: 260, height: 260 });
  const frame = await faceFrame(page);
  const zs = () => frame.evaluate(() => ({ ...(window.__faceZs || {}), st: LIVE_STATE, off: LIVE_OFFLINE }));

  // Standby, by hand or by the schedule: the same state here.
  await page.evaluate((l) => window.__emit("jarvis-link", { ...l, power: "standby", power_set_by: "override" }), LIVE);
  await page.waitForTimeout(5000);          // nodding off takes a couple of seconds
  const asleep = await zs();
  const litAsleep = await frame.evaluate(ZS_REGION);

  // The link drops: standby still, but with the ring and no Zs.
  await page.evaluate((l) => window.__emit("jarvis-link",
    { ...l, power: "standby", connected: false, stale: true, error: "stream closed" }), LIVE);
  await page.waitForTimeout(13200);         // the 12 s grace, then the half-second fade
  const offline = await zs();
  const litOffline = await frame.evaluate(ZS_REGION);

  // Back, still on standby: the Zs come back.
  await page.evaluate((l) => window.__emit("jarvis-link", { ...l, power: "standby" }), LIVE);
  await page.waitForTimeout(1200);
  const back = await zs();

  // Awake: none.
  await page.evaluate((l) => window.__emit("jarvis-link", l), LIVE);
  await page.waitForTimeout(3000);
  const awake = await zs();
  await page.close();

  assert.equal(asleep.st, "standby");
  assert.ok(asleep.asleep > 0.9 && asleep.shown >= 1, `no Zs asleep: ${JSON.stringify(asleep)}`);
  assert.equal(offline.st, "standby");
  assert.equal(offline.off, true);
  assert.equal(offline.shown, 0, `Zs while not connected: ${JSON.stringify(offline)}`);
  assert.ok(offline.asleep < 0.002);
  assert.ok(litAsleep > litOffline + 60, `nothing drawn where the Zs rise: ${litAsleep} vs ${litOffline}`);
  assert.ok(back.asleep > 0.9 && back.shown >= 1, `the Zs did not come back: ${JSON.stringify(back)}`);
  assert.equal(awake.st, "idle");
  assert.ok(awake.shown === 0 && awake.asleep < 0.05, `Zs while awake: ${JSON.stringify(awake)}`);
  assert.deepEqual(page.__errors, []);
});

/** The Faces window, its own loop stopped and its clock in the test's hands. */
async function editor(prep, context) {
  // `context`: one the test made, to share its storage between pages (a page
  // from browser.newPage gets a context, and a storage, of its own).
  const page = context ? await context.newPage() : await browser.newPage({ viewport: { width: 700, height: 600 } });
  if (prep) await prep(page);
  await page.goto(`${base}/faces.html`, { timeout: 90000 });
  await page.waitForFunction(() => typeof drawSurface === "function" && typeof CritterPose !== "undefined",
    null, { timeout: 90000 });
  await page.evaluate(() => { frame = function () {}; });
  await page.waitForTimeout(1200);
  await page.evaluate(() => {
    let fake = performance.now();
    performance.now = () => fake;
    window.__adv = (ms) => { fake += ms; };
    gpuJudge = () => {}; gpuTrip = () => {};
    window.__surface = (id) => {
      const cv = document.createElement("canvas");
      cv.style.width = "240px"; cv.style.height = "240px";
      document.body.appendChild(cv);
      const s = makeSurface(THEME[id], cv, null);
      sizeSurface(s);
      return s;
    };
    window.__run = (s, st, secs, each) => {
      const out = [];
      for (let i = 0; i < Math.round(secs * 30); i++) {
        __adv(1000 / 30); drawSurface(s, 1 / 30, st);
        if (each) out.push(each(s));
      }
      return out;
    };
  });
  return page;
}

await check("the Zs come from the point beside the head, so they follow its breathing and the camera", async () => {
  const page = await editor();
  const got = await page.evaluate(() => {
    const s = __surface("redpanda");
    __run(s, "standby", 6);
    const ys = __run(s, "standby", 4, () => window.__faceZs.y);
    const x0 = window.__faceZs.x;
    s.view.yaw = 0.5;
    __run(s, "standby", 0.2);
    return { spread: Math.max(...ys) - Math.min(...ys), x0, x1: window.__faceZs.x, shown: window.__faceZs.shown };
  });
  await page.close();
  assert.ok(got.shown >= 1, JSON.stringify(got));
  assert.ok(got.spread > 0.002, `the Zs' point stood still while it breathed: ${JSON.stringify(got)}`);
  assert.ok(Math.abs(got.x1 - got.x0) > 0.05, `the Zs' point did not turn with the camera: ${JSON.stringify(got)}`);
});

await check("reduced motion: one still z, no rising ones", async () => {
  const page = await editor((p) => p.emulateMedia({ reducedMotion: "reduce" }));
  const got = await page.evaluate(() => {
    const s = __surface("pygmyowl");
    __run(s, "standby", 6);
    return __run(s, "standby", 3, () => window.__faceZs.shown);
  });
  await page.close();
  assert.ok(got.every((n) => n === 1), `under reduced motion: ${JSON.stringify(got)}`);
});

await check("a link that comes back straight into an awake state never flashes the Zs while the animal wakes", async () => {
  // The host's offline fade used to come back in (over half a second) at the
  // same moment the waking pose's own asleep weight was falling (over ~0.7
  // s): the Zs showed again for a moment during the wake-up. The offline
  // weight now comes back only on standby (zsStep).
  const page = await editor();
  const got = await page.evaluate(() => {
    const s = __surface("redpanda");
    __run(s, "standby", 8);
    s.offline = true;
    __run(s, "standby", 1.5);
    const gone = window.__faceZs.asleep;
    s.offline = false;
    const waking = __run(s, "idle", 3, () => ({ a: window.__faceZs.asleep, n: window.__faceZs.shown }));
    const zsR = THEME.redpanda.mem.get(s.view).zsR;
    __run(s, "standby", 6);
    const again = { a: window.__faceZs.asleep, n: window.__faceZs.shown };
    const rule = [zsStep(0.5, true, true, 0.1), zsStep(0.5, false, true, 0.1), zsStep(0.5, false, false, 0.1)];
    return { gone, worst: Math.max(...waking.map((w) => w.a)), shown: Math.max(...waking.map((w) => w.n)), zsR, again, rule };
  });
  const errors = page.__errors;
  await page.close();
  assert.ok(got.gone < 0.002, `Zs while not connected: ${JSON.stringify(got)}`);
  assert.ok(got.worst <= 0.002 && got.shown === 0, `the Zs came back while it woke: ${JSON.stringify(got)}`);
  assert.equal(got.zsR, 0, "the offline weight came back while awake");
  assert.ok(got.again.a > 0.99 && got.again.n >= 1, `no Zs the next time it slept: ${JSON.stringify(got)}`);
  assert.deepEqual(got.rule.map((x) => +x.toFixed(6)), [0.4, 0.6, 0.5]);
  assert.deepEqual(errors || [], []);
});

await check("standby's dim follows the animal nodding off and waking; banked and error are unchanged", async () => {
  // The whole animal used to dim as soon as standby started, while its pose
  // took ~3 s to nod off, and brighten at once on waking while it took ~2 s
  // to wake. Standby's dim now follows the pose's asleep weight (sleepDim).
  const page = await editor();
  const got = await page.evaluate(() => {
    const out = {};
    for (const id of ["redpanda", "pygmyowl", "seaotter"]) {
      const s = __surface(id);
      const dim = () => FACE_DIM;
      __run(s, "idle", 3);
      const off = __run(s, "standby", 4, dim);
      const wake = __run(s, "idle", 3, dim);
      const banked = __run(s, "banked", 1, dim);
      const toSleep = __run(s, "standby", 4, dim);
      __run(s, "idle", 3);
      const error = __run(s, "error", 1, dim);
      out[id] = { off, wake, banked: banked[banked.length - 1], toSleep, error: error[error.length - 1] };
    }
    return { out, standby: STATE_FX.standby.dim, bankedDim: STATE_FX.banked.dim, errorDim: STATE_FX.error.dim,
             rule: [sleepDim(1, 0), sleepDim(1, 1), sleepDim(0.45, 1), sleepDim(1, 0.5)] };
  });
  const errors = page.__errors;
  await page.close();
  const sb = got.standby;
  for (const [id, d] of Object.entries(got.out)) {
    assert.ok(d.off[15] > 0.97, `${id} dimmed before it nodded off: ${d.off[15]}`);
    for (let i = 1; i < d.off.length; i++) assert.ok(d.off[i] <= d.off[i - 1] + 1e-6, `${id} brighter at frame ${i} while nodding off`);
    assert.ok(Math.abs(d.off[d.off.length - 1] - sb) < 1e-4, `${id} asleep at ${d.off[d.off.length - 1]}`);
    assert.ok(d.wake[0] < sb + 0.05, `${id} brightened at once on waking: ${d.wake[0]}`);
    for (let i = 1; i < d.wake.length; i++) assert.ok(d.wake[i] >= d.wake[i - 1] - 1e-6, `${id} darker at frame ${i} while waking`);
    assert.ok(Math.abs(d.wake[d.wake.length - 1] - 1) < 1e-4, `${id} awake at ${d.wake[d.wake.length - 1]}`);
    assert.ok(Math.abs(d.banked - got.bankedDim) < 1e-3, `${id} banked at ${d.banked}`);
    assert.ok(d.toSleep.every((x) => x >= got.bankedDim - 1e-3 && x <= sb + 1e-4), `${id} jumped on falling asleep from banked`);
    assert.ok(Math.abs(d.error - got.errorDim) < 1e-3, `${id} error at ${d.error}`);
  }
  assert.deepEqual(got.rule.map((x) => +x.toFixed(6)), [1, sb, sb, 0.8]);
  assert.deepEqual(errors || [], []);
});

await check("Keep the animal still: shared with the phone, set in Settings' Animal options, read by every face page, eased into the pose", async () => {
  // Settings sends it to the PC (set_animal) and keeps the PC's answer in
  // this computer's storage for the face pages...
  const settings = await K.open(browser, base, "settings.html", {}, { width: 760, height: 1400 });
  await settings.waitForSelector("#animal-still", { timeout: 15000 });
  assert.equal(await settings.locator("#animal-still").isChecked(), false, "off by default");
  await settings.locator("#animal-still").check();
  await settings.waitForFunction(() => /still/.test(document.getElementById("animal-status").textContent));
  const sent = await settings.evaluate(() => window.__calls.filter(([c]) => c === "set_animal").map(([, a]) => a.change));
  assert.deepEqual(sent, [{ still: true }], "ONE change, to the PC");
  const saved = await settings.evaluate(() => JSON.parse(localStorage.getItem("jarvis.animal.v1")));
  assert.equal(saved.still, true);
  assert.equal(await settings.locator("#animal-still").isChecked(), true);
  assert.deepEqual(settings.__errors, []);
  await settings.close();

  // ...a face page opened afterwards starts with it (the same storage,
  // shared by every page of this computer's origin)...
  const context = await browser.newContext({ viewport: { width: 700, height: 600 } });
  await context.addInitScript((v) => localStorage.setItem("jarvis.animal.v1", v), JSON.stringify(saved));
  const page = await editor(null, context);
  const start = await page.evaluate(() => FACE_STILL);
  const eased = await page.evaluate(() => {
    const s = __surface("seaotter");
    const r = __run(s, "idle", 1.2, (s) => THEME.seaotter.mem.get(s.view).stillR);
    return { first: r[0], last: r[r.length - 1] };
  });
  // ...and a face page already open follows when another window stores the
  // PC's new value (the phone turned it off, say).
  const other = await context.newPage();
  await other.goto(`${base}/faces.html?mode=display&face=arc`, { timeout: 90000 });
  await other.evaluate((v) => localStorage.setItem("jarvis.animal.v1", v), JSON.stringify({ ...saved, still: false }));
  await page.waitForTimeout(400);
  const after = await page.evaluate(() => FACE_STILL);
  await context.close();

  assert.equal(start, true, "the Faces window did not read the shared choice");
  assert.ok(eased.first >= 0.99 && eased.last === 1, `still did not reach the pose: ${JSON.stringify(eased)}`);
  assert.equal(after, false, "an open face page did not hear the change");
});

await check("this computer's old Still: still counts until it has reached the PC, then the PC's value rules", async () => {
  const context = await browser.newContext({ viewport: { width: 700, height: 600 } });
  await context.addInitScript(() => {
    localStorage.setItem("jarvis.faceTuning", JSON.stringify({ quality: "high", frameRate: "auto", speed: 1, autoAdjust: true, still: true }));
    localStorage.removeItem("jarvis.animal.v1");
    localStorage.removeItem("jarvis.animal.migrated");
  });
  const page = await editor(null, context);
  const olderPc = await page.evaluate(() => FACE_STILL);
  // The PC answers "off" but the old "on" has not reached it yet: still on.
  await page.evaluate(() => localStorage.setItem("jarvis.animal.v1", JSON.stringify({ still: false })));
  const other = await context.newPage();
  await other.goto(`${base}/faces.html?mode=display&face=arc`, { timeout: 90000 });
  await other.evaluate(() => localStorage.setItem("jarvis.animal.v1", JSON.stringify({ still: false, nods: true })));
  await page.waitForTimeout(300);
  const pending = await page.evaluate(() => FACE_STILL);
  await other.evaluate(() => localStorage.setItem("jarvis.animal.migrated", "1"));
  await page.waitForTimeout(300);
  const moved = await page.evaluate(() => FACE_STILL);
  await context.close();
  assert.equal(olderPc, true, "an older PC: this computer's own Still counts");
  assert.equal(pending, true, "the old 'on' was lost before it reached the PC");
  assert.equal(moved, false, "after the move the PC's value did not rule");

  // The move itself: the first window that hears the PC sends it, once.
  const p2 = await K.open(browser, base, "settings.html", {
    storage: { "jarvis.faceTuning": JSON.stringify({ still: true }), "jarvis.animal.migrated": null },
  }, { width: 760, height: 900 });
  await p2.waitForFunction(() => localStorage.getItem("jarvis.animal.migrated") === "1", null, { timeout: 15000 });
  const calls = await p2.evaluate(() => window.__calls.filter(([c]) => c === "__migratedStill").length);
  const errs = p2.__errors;
  await p2.close();
  assert.deepEqual(errs, []);
  assert.equal(calls, 1, "the old Still was not sent to the PC exactly once");
});

await check("an older PC: Settings offers Keep the animal still on this computer only, and says so", async () => {
  const page = await K.open(browser, base, "settings.html", { animal: null }, { width: 760, height: 1200 });
  await page.waitForSelector("#animal-still", { timeout: 15000 });
  assert.match(await page.textContent("#animal-state"), /cannot share the animal options yet/);
  assert.equal(await page.locator("#animal-switches input").count(), 1, "only Still, locally");
  assert.match(await page.textContent('[data-animal="still"]'), /this computer only/);
  await page.locator("#animal-still").check();
  const saved = await page.evaluate(() => JSON.parse(localStorage.getItem("jarvis.faceTuning")));
  const sent = await page.evaluate(() => window.__calls.filter(([c]) => c === "set_animal").length);
  await page.close();
  assert.equal(saved.still, true);
  assert.equal(sent, 0, "nothing was sent to a PC that cannot take it");
});

await check("the monkey does what every animal does: sleeps with Zs, none offline, wakes, Still and serious ease in", async () => {
  // The owner (2026-09-28): the fourth animal must do everything the other
  // three can. Its own face page, its own pose: nodding off and waking,
  // the Zs (and none while not connected), Still and a serious moment eased
  // into its pose, and no errors along the way.
  const page = await editor();
  const got = await page.evaluate(() => {
    const s = __surface("monkey");
    const m = () => THEME.monkey.mem.get(s.view);
    __run(s, "idle", 2);
    const awake = window.__faceZs ? window.__faceZs.shown : 0;
    const early = __run(s, "standby", 1.5, () => window.__faceZs.shown);
    __run(s, "standby", 5);
    const asleep = { shown: window.__faceZs.shown, a: window.__faceZs.asleep };
    s.offline = true;
    __run(s, "standby", 1.5);
    const offline = { shown: window.__faceZs.shown, a: window.__faceZs.asleep };
    s.offline = false;
    __run(s, "standby", 1.5);
    const back = window.__faceZs.shown;
    __run(s, "idle", 3);
    const woke = { shown: window.__faceZs.shown, a: window.__faceZs.asleep };
    FACE_STILL = true;
    const still = __run(s, "idle", 1.2, () => m().stillR);
    FACE_STILL = false;
    setSerious(true);
    const serious = __run(s, "idle", 1.2, () => m().seriousR);
    setSerious(false);
    return { awake, early: Math.max(...early), asleep, offline, back, woke,
             still: [still[0], still[still.length - 1]], serious: [serious[0], serious[serious.length - 1]] };
  });
  const errors = page.__errors;
  await page.close();
  assert.equal(got.early, 0, `Zs before it was asleep: ${JSON.stringify(got)}`);
  assert.ok(got.asleep.shown >= 1 && got.asleep.a > 0.99, `no Zs asleep: ${JSON.stringify(got)}`);
  assert.ok(got.offline.shown === 0 && got.offline.a < 0.002, `Zs while not connected: ${JSON.stringify(got)}`);
  assert.ok(got.back >= 1, `the Zs did not come back: ${JSON.stringify(got)}`);
  assert.ok(got.woke.shown === 0 && got.woke.a < 0.05, `Zs after waking: ${JSON.stringify(got)}`);
  assert.ok(got.still[0] < 0.1 && got.still[1] === 1, `Still did not ease in: ${JSON.stringify(got)}`);
  assert.ok(got.serious[0] < 0.1 && got.serious[1] === 1, `serious did not ease in: ${JSON.stringify(got)}`);
  assert.deepEqual(errors || [], []);
});

await check("Keep the animal still changes nothing on a face that is not an animal", async () => {
  const page = await editor();
  const same = await page.evaluate(() => {
    const pic = (still) => {
      FACE_STILL = still;
      const s = __surface("arc");
      s.seed = 3;
      __run(s, "idle", 1);
      const d = s.canvas.getContext("2d").getImageData(0, 0, s.canvas.width, s.canvas.height).data;
      let h = 0;
      for (let i = 0; i < d.length; i += 7) h = (h * 31 + d[i]) >>> 0;
      return h;
    };
    // The same clock for both.
    const t0 = performance.now();
    const a = pic(false);
    __adv(t0 - performance.now());
    const b = pic(true);
    FACE_STILL = false;
    return a === b;
  });
  await page.close();
  assert.equal(same, true, "the Arc face drew differently with Still on");
});

await check("a serious moment reaches the floating face through jarvis-link.js", async () => {
  const page = await K.open(browser, base, "floating.html", { appearance: PANDA }, { width: 240, height: 240 });
  const frame = await faceFrame(page);
  await page.evaluate((l) => window.__emit("jarvis-link", l), LIVE);
  await page.evaluate(() => window.__emit("jarvis-event", { kind: "wellbeing", id: 1, data: { serious: true } }));
  await page.waitForTimeout(300);
  const on = await frame.evaluate(() => faceSerious());
  await page.evaluate(() => window.__emit("jarvis-event", { kind: "wellbeing", id: 2, data: { serious: false } }));
  await page.waitForTimeout(300);
  const off = await frame.evaluate(() => faceSerious());
  // Not a word: anything but a boolean is ignored.
  await page.evaluate(() => window.__emit("jarvis-event", { kind: "wellbeing", id: 3, data: { serious: "yes" } }));
  await page.waitForTimeout(300);
  const junk = await frame.evaluate(() => faceSerious());
  await page.close();
  assert.equal(on, true, "the floating face did not go serious");
  assert.equal(off, false, "the floating face stayed serious");
  assert.equal(junk, false);
});

await check("jarvis-link.js: faceSignal carries serious, and the 900 s net ends it", async () => {
  const L = await import("../src/jarvis-link.js");
  const heard = [];
  const stop = L.onSerious((v) => heard.push(v));
  const t = Date.now();
  L.noteWellbeing({ kind: "wellbeing", data: { serious: true } }, t);
  assert.equal(L.faceSignal(undefined, t + 1000).serious, true);
  assert.equal(L.faceSerious(t + L.SERIOUS_NET_MS - 1), true);
  assert.equal(L.faceSerious(t + L.SERIOUS_NET_MS + 1), false, "no 900 s safety net");
  L.noteWellbeing({ kind: "wellbeing", data: { serious: false } }, t + 2000);
  assert.equal(L.faceSignal(undefined, t + 2001).serious, false);
  L.noteWellbeing({ kind: "approval", data: { serious: true } }, t + 3000);
  assert.equal(L.faceSerious(t + 3001), false, "another kind of event turned it on");
  stop();
  assert.deepEqual(heard, [true, false]);
  for (const f of ["widget.js", "floating.js"]) {
    const src = (await import("node:fs")).readFileSync(new URL(`../src/${f}`, import.meta.url), "utf8");
    assert.match(src, /onSerious\(\(\) => postFace\(\)\)/, `${f} does not post again when it changes`);
  }
});

await browser.close();
close();
if (fails.length) { console.log(`\n${fails.length} failed`); process.exit(1); }
console.log("\nall animal-options checks passed");
