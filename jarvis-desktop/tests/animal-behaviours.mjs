/**
 * The new animal behaviours, as the desktop feeds them (the owner's decisions
 * of 2026-09-28; docs/CRITTERS.md "What each app feeds them"). The pose code
 * that plays them is checked against the phone's by CritterPoseTest; this is
 * the host's side:
 *
 *  - face-moments.js: a fact saved, a long answer ready and a focus session
 *    reach the face frames, and a fact's nod NEVER while App lock or "Hide
 *    memory lists and chat history" is on - or before it is known (fails
 *    closed); a replayed event never nods twice; the Widget, the floating
 *    face and the HUD all relay them, and may read the two lock answers;
 *  - faces.html hands the pose every input: variety, the owner's switches
 *    (eased), the pauses in the owner's talking (listening) and in Jarvis's
 *    real voice (speaking - only when a real voice starts the answer), the
 *    moments as "seconds since", a focus session and its stretch once idle,
 *    being stroked (a press that moves, or is held), and the frame pacer's
 *    cute moments;
 *  - switching faces: the leaving animal's goodbye, then the new one's
 *    hello; a face that is not a character fades on its side; under calm
 *    motion a character cross-fades; two instruments switch at once.
 *
 * Part 1 needs no browser; part 2 opens the real faces.html in display
 * mode (the Widget's face).
 *
 *     node tests/animal-behaviours.mjs
 */
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

const fails = [];
const check = async (name, fn) => {
  try { await fn(); console.log(`ok    ${name}`); }
  catch (e) { fails.push(name); console.log(`FAIL  ${name}\n      ${e.message}`); }
};
const src = (p) => readFileSync(new URL(`../${p}`, import.meta.url), "utf8");
const M = await import("../src/face-moments.js");

// ---- Part 1: the relay's rules ----------------------------------------------------

await check("a saved fact nods only when both locks are known to be off", () => {
  const frame = { kind: "memory_saved", data: { ids: [11] } };
  assert.equal(M.quietOf(null), true, "not known yet: quiet");
  assert.equal(M.quietOf({ appLock: true, privateAnswers: false }), true);
  assert.equal(M.quietOf({ appLock: false, privateAnswers: true }), true);
  assert.equal(M.quietOf({ appLock: false, privateAnswers: false }), false);
  assert.deepEqual(M.momentOf(frame, false, new Set()), { kind: "fact" });
  assert.equal(M.momentOf(frame, true, new Set()), null);
  // A replayed event (a reconnect) never nods twice - even one heard while quiet.
  const seen = new Set();
  assert.equal(M.momentOf({ kind: "memory_saved", data: { ids: [5] } }, true, seen), null);
  assert.equal(M.momentOf({ kind: "memory_saved", data: { ids: [5] } }, false, seen), null);
  assert.deepEqual(M.momentOf({ kind: "memory_saved", data: { ids: [5, 6] } }, false, seen), { kind: "fact" });
  assert.equal(M.momentOf({ kind: "memory_saved", data: {} }, false, new Set()), null);
});

await check("a long answer ready glows; a focus session starts and ends; nothing else is a moment", () => {
  assert.deepEqual(M.momentOf({ kind: "deep", data: { id: "d", state: "done" } }, true), { kind: "glow" });
  assert.equal(M.momentOf({ kind: "deep", data: { id: "d", state: "failed" } }, true), null);
  assert.deepEqual(M.momentOf({ kind: "focus", data: { state: "started" } }, true), { kind: "focus", on: true });
  assert.deepEqual(M.momentOf({ kind: "focus", data: { state: "changed" } }, true), { kind: "focus", on: true });
  assert.deepEqual(M.momentOf({ kind: "focus", data: { state: "ended" } }, true), { kind: "focus", on: false });
  assert.equal(M.momentOf({ kind: "focus", data: { state: "callout", seq: 2 } }, true), null);
  assert.equal(M.momentOf({ kind: "activity", data: {} }, false), null);
  assert.equal(M.momentOf(null, false), null);
});

await check("the relay: the lock answer first, then security-changed; only the kind is posted", async () => {
  const posted = [];
  const handlers = {};
  let loaded = null;
  const frame = { contentWindow: { postMessage: (m) => posted.push(m) },
                  addEventListener: (e, fn) => { if (e === "load") loaded = fn; } };
  let asked = null;
  M.relayFaceMoments(frame, (name, fn) => { handlers[name] = fn; },
    async (cmd) => { asked = cmd; return { appLock: false, privateAnswers: false }; });
  handlers[M.BUS_EVENT]({ payload: { kind: "memory_saved", data: { ids: [1] } } });
  assert.equal(posted.length, 0, "before the lock answer arrives: no nod");
  await new Promise((r) => setTimeout(r, 10));
  assert.equal(asked, "get_lock_flags");
  handlers[M.BUS_EVENT]({ payload: { kind: "memory_saved", data: { ids: [2] } } });
  assert.deepEqual(posted.at(-1), { type: M.FACE_MOMENT_MESSAGE, kind: "fact" });
  handlers[M.SECURITY_EVENT]({ payload: { appLock: true, privateAnswers: false, approvals: "risky" } });
  handlers[M.BUS_EVENT]({ payload: { kind: "memory_saved", data: { ids: [3] } } });
  assert.equal(posted.length, 1, "App lock on: no nod");
  handlers[M.SECURITY_EVENT]({ payload: { appLock: false, privateAnswers: true } });
  handlers[M.BUS_EVENT]({ payload: { kind: "memory_saved", data: { ids: [4] } } });
  assert.equal(posted.length, 1, "Hide memory lists on: no nod");
  handlers[M.BUS_EVENT]({ payload: { kind: "focus", data: { state: "started" } } });
  loaded();
  assert.deepEqual(posted.slice(-2), [{ type: M.FACE_MOMENT_MESSAGE, kind: "focus", on: true },
                                      { type: M.FACE_MOMENT_MESSAGE, kind: "focus", on: true }],
    "a frame that loads is told a focus session is on");
  for (const m of posted) assert.deepEqual(Object.keys(m).sort().filter((k) => !["type", "kind", "on"].includes(k)), []);
});

await check("every window with a face relays them, and may read the two lock answers", () => {
  for (const f of ["src/widget.js", "src/floating.js", "src/jarvis_hud.html"]) {
    assert.match(src(f), /relayFaceMoments\(/, f);
  }
  const toml = src("src-tauri/permissions/surfaces.toml");
  for (const set of ["jarvis-link", "hud-link"]) {
    const at = toml.slice(toml.indexOf(`identifier = "${set}"`));
    assert.match(at.slice(0, at.indexOf("]")), /"allow-get-lock-flags"/, set);
  }
  assert.match(src("src-tauri/build.rs"), /"get_lock_flags"/);
  assert.match(src("src-tauri/src/lib.rs"), /commands::get_lock_flags/);
  // Two yes/no answers, nothing else from the settings.
  const rs = src("src-tauri/src/commands.rs");
  const fn = rs.slice(rs.indexOf("pub fn get_lock_flags"), rs.indexOf("pub fn get_lock_flags") + 300);
  assert.match(fn, /"appLock": s\.app_lock, "privateAnswers": s\.private_answers \}/);
});

// ---- Part 2: the page (needs Playwright) --------------------------------------------

let K = null;
try { await import("playwright"); K = await import("./uikit.mjs"); } catch (e) { K = null; }
if (!K) {
  console.log("skip  the face page (Playwright is not installed - see tests/README.md)");
} else {
  const { base, close } = await K.serve();
  const browser = await K.launch();
  const open = async (face = "redpanda", opts = {}) => {
    const ctx = await browser.newContext({ viewport: { width: 300, height: 300 },
                                           reducedMotion: opts.reduced ? "reduce" : "no-preference" });
    const page = await ctx.newPage();
    if (opts.animal) {
      await page.addInitScript((a) => localStorage.setItem("jarvis.animal.v1", JSON.stringify(a)), opts.animal);
    }
    await page.goto(`${base}/faces.html?mode=display&feed=parent&face=${face}`);
    await page.waitForFunction(() => window.__faceSwitch && window.__faceOpts, null, { timeout: 60000 });
    return { page, done: () => ctx.close() };
  };
  const post = (page, m) => page.evaluate((x) => window.postMessage(x, location.origin), m);
  const opts = (page) => page.evaluate(() => window.__faceOpts);
  // Waits (up to 30 s: a shader can take seconds to build on a busy machine)
  // for a hello to be playing, and returns the switch state AT THAT MOMENT.
  const helloSeen = async (page) => {
    const h = await page.waitForFunction(() => {
      const n = window.__faceSwitch.now();
      // Any moment of the hello (progress 0 up to 1): on a slow machine one
      // frame can jump from "not started" straight to "over".
      return n.phase === "hello" && n.switching ? JSON.parse(JSON.stringify(n)) : false;
    }, null, { timeout: 30000 });
    return h.jsonValue();
  };
  // Holds every request for `glob` until release() - the page's read of the
  // stored options, say, until the test has seen a frame drawn without them.
  const hold = async (page, glob) => {
    let release;
    const gate = new Promise((r) => { release = r; });
    await page.route(glob, async (route) => { await gate; await route.continue(); });
    return { release };
  };

  await check("the pose is handed variety and the owner's switches, eased", async () => {
    const { page, done } = await open("redpanda", { animal: { nods: false, cute_moments: false } });
    await page.waitForTimeout(400);
    const o = await opts(page);
    await done();
    assert.equal(o.variety, 1);
    assert.equal(o.nods, 0);
    assert.equal(o.cute_moments, 0);
    assert.equal(o.acks, 1);
    assert.equal(o.petting, 1);
    assert.equal(o.focus_buddy, 1);
    assert.ok(!("heardN" in o) || o.heardN >= 0);
  });

  await check("a face drawn before the stored switches are read takes them at once, never easing from the defaults", async () => {
    // A slow start: hold the page's read of the stored options back until
    // the face has been drawing for a while (the race that once left a
    // switched-off behaviour at 9% on a busy machine).
    const ctx = await browser.newContext({ viewport: { width: 300, height: 300 } });
    const page = await ctx.newPage();
    await page.addInitScript(() => localStorage.setItem("jarvis.animal.v1",
      JSON.stringify({ nods: false, cute_moments: false, still: true })));
    // Held until the first frame has been drawn (not for a fixed time: on a
    // slow run a fixed 1.5 s could run out before the first frame, and the
    // check then saw the stored values from the start - 2 runs in 13).
    const read = await hold(page, "**/animal-shared.js");
    await page.goto(`${base}/faces.html?mode=display&feed=parent&face=redpanda`, { waitUntil: "commit" });
    await page.waitForFunction(() => window.__faceOpts, null, { timeout: 60000 });
    const early = await opts(page);
    // Every value the pose is handed, frame by frame, until the read lands.
    await page.evaluate(() => {
      window.__nodsSeen = [];
      const tick = () => { if (window.__faceOpts) window.__nodsSeen.push(window.__faceOpts.nods);
                           requestAnimationFrame(tick); };
      requestAnimationFrame(tick);
    });
    await page.waitForTimeout(300);
    read.release();
    await page.waitForFunction(() => window.__faceOpts && window.__faceOpts.nods === 0, null, { timeout: 30000 });
    await page.waitForTimeout(200);
    const seen = await page.evaluate(() => window.__nodsSeen);
    const late = await opts(page);
    await ctx.close();
    assert.equal(early.nods, 1, "drawn before the read, with the defaults");
    assert.equal(late.nods, 0);
    assert.equal(late.cute_moments, 0);
    const between = seen.filter((v) => v > 0 && v < 1);
    assert.deepEqual(between, [], "no eased values on the way from the defaults to the stored switches");
  });

  await check("a fact saved and a long answer ready reach the pose as seconds since, never closer than the pose allows", async () => {
    const { page, done } = await open();
    await post(page, { type: "jarvis-face-moment", kind: "fact" });
    await page.waitForTimeout(100);
    const first = await page.evaluate(() => FACE_MOMENTS.factAt);
    await page.waitForTimeout(200);
    await post(page, { type: "jarvis-face-moment", kind: "fact" });
    await post(page, { type: "jarvis-face-moment", kind: "glow" });
    await page.waitForTimeout(100);
    const second = await page.evaluate(() => FACE_MOMENTS.factAt);
    await page.waitForTimeout(1300);
    await post(page, { type: "jarvis-face-moment", kind: "fact" });
    await page.waitForTimeout(100);
    const third = await page.evaluate(() => FACE_MOMENTS.factAt);
    // The pose's own copy, from the last frame drawn (a frame or two old).
    await page.waitForTimeout(300);
    const o = await opts(page);
    await done();
    assert.ok(first > 0);
    assert.equal(second, first, "a second fact within 1.2 s does not restart the nod");
    assert.ok(third > first + 1200, "one after the gap does");
    assert.ok(o.ackNod >= 0 && o.ackNod < 1.2, `the pose is handed seconds since: ${o.ackNod}`);
    assert.ok(o.ackGlow > 1 && o.ackGlow < 3, `glow ${o.ackGlow}`);
  });

  await check("a focus session eases in; its stretch waits for idle", async () => {
    const { page, done } = await open();
    await post(page, { type: "jarvis-hud-face", state: "idle" });
    await post(page, { type: "jarvis-face-moment", kind: "focus", on: true });
    await page.waitForTimeout(1400);
    const on = await opts(page);
    await post(page, { type: "jarvis-hud-face", state: "thinking" });
    await post(page, { type: "jarvis-face-moment", kind: "focus", on: false });
    await page.waitForTimeout(400);
    const busy = await opts(page);
    await post(page, { type: "jarvis-hud-face", state: "idle" });
    await page.waitForTimeout(400);
    const idle = await opts(page);
    await done();
    assert.equal(on.focus, 1);
    assert.ok(!("focusEnd" in busy), "no stretch while Jarvis is busy");
    assert.ok(idle.focusEnd >= 0 && idle.focusEnd < 1, `the stretch, once idle: ${idle.focusEnd}`);
  });

  await check("listening: the owner's pauses are counted; speaking: phrase ends only for a real voice", async () => {
    const { page, done } = await open();
    // (Its own talking gestures held off, so the switch to phrase ends is
    // not kept waiting for one - the next check covers that.)
    await page.evaluate(() => { CritterPose.species.redpanda.gesturing = () => false; });
    await post(page, { type: "jarvis-hud-face", state: "listening" });
    for (let i = 0; i < 26; i++) {
      await post(page, { type: "jarvis-face-voice", mic: i < 16 ? 0.4 : 0 });
      await page.waitForTimeout(60);
    }
    const heard = await opts(page);
    // A typed answer: no real voice as it starts.
    await post(page, { type: "jarvis-hud-face", state: "speaking" });
    await page.waitForTimeout(200);
    const typed = await opts(page);
    await post(page, { type: "jarvis-hud-face", state: "idle" });
    await page.waitForTimeout(200);
    // A spoken one - in the order the app sees it: the face turns to
    // speaking as the answer's text starts streaming, and the voice is
    // heard a moment later.
    await post(page, { type: "jarvis-hud-face", state: "speaking" });
    await page.waitForTimeout(200);
    for (let i = 0; i < 24; i++) {
      await page.evaluate((v) => setSpeechLevel(v), i < 16 ? 0.4 : 0);
      await page.waitForTimeout(60);
    }
    const spoken = await opts(page);
    await done();
    assert.ok(heard.heardN >= 1 && heard.heard < 1.5, JSON.stringify([heard.heardN, heard.heard]));
    assert.ok(!("phraseN" in typed), "a typed answer keeps the gestures' own timing");
    assert.ok(spoken.phraseN >= 1 && spoken.phraseEnd < 1.2, JSON.stringify([spoken.phraseN, spoken.phraseEnd]));
  });

  await check("speaking: phrase gestures switch on at the first real voice, never over a gesture, and off when speaking ends", async () => {
    const { page, done } = await open();
    // Stand in for the panda's own gesture timing, to hold one "playing".
    await page.evaluate(() => { window.__gest = true; CritterPose.species.redpanda.gesturing = () => window.__gest; });
    await post(page, { type: "jarvis-hud-face", state: "speaking" });
    await page.waitForTimeout(250);
    const text = await opts(page);
    const voice = async () => {
      for (let i = 0; i < 6; i++) { await page.evaluate(() => setSpeechLevel(0.4)); await page.waitForTimeout(60); }
    };
    await voice();
    const overGesture = await opts(page);
    await page.evaluate(() => { window.__gest = false; });
    await voice();
    const on = await opts(page);
    await post(page, { type: "jarvis-hud-face", state: "idle" });
    await page.waitForTimeout(200);
    const after = await opts(page);
    await done();
    assert.ok(!("phraseN" in text), "text streaming, nothing heard yet: the gestures' own timing");
    assert.ok(!("phraseN" in overGesture), "not while one of its own gestures plays");
    assert.ok("phraseN" in on && on.phraseN >= 0, "on once a voice is heard and no gesture plays");
    assert.ok(!("phraseN" in after), "off once the speaking stretch ends");
  });

  await check("switching back to a face shown earlier takes today's options at once", async () => {
    const { page, done } = await open("redpanda");
    await page.waitForTimeout(300);
    await page.evaluate(() => window.__faceSwitch.to("pygmyowl"));
    await page.waitForFunction(() => { const n = window.__faceSwitch.now(); return n.face === "pygmyowl" && n.phase === null; },
      null, { timeout: 30000 });
    // "Keep the animal still" turned on while the panda is not shown, and
    // the owl settled into it.
    await page.evaluate(() => applyFaceStill({ still: true }));
    await page.waitForTimeout(1500);
    await page.evaluate(() => {
      window.__stillSeen = [];
      const tick = () => { if (window.__faceOpts) window.__stillSeen.push(window.__faceOpts.still);
                           requestAnimationFrame(tick); };
      requestAnimationFrame(tick);
    });
    await page.evaluate(() => window.__faceSwitch.to("redpanda"));
    await page.waitForFunction(() => { const n = window.__faceSwitch.now(); return n.face === "redpanda" && n.phase === null; },
      null, { timeout: 30000 });
    await page.waitForTimeout(200);
    const seen = await page.evaluate(() => window.__stillSeen);
    await done();
    assert.ok(seen.length > 10, `frames seen: ${seen.length}`);
    assert.deepEqual(seen.filter((v) => v !== 1), [], "the panda came back eased toward Still from where it was left");
  });

  await check("a face that has just opened has not rested yet; one opening straight into waiting on you has nothing to react to", async () => {
    const { page, done } = await open("robot");
    // What the pose is told, frame by frame: seconds in the state (for idle,
    // how long it has rested - the cute moments' and the zip's gate).
    await page.evaluate(() => {
      for (const id of Object.keys(CritterPose.species)) {
        const sp = CritterPose.species[id], p = sp.pose;
        sp.pose = function (...a) { window.__since = [id, a[0], a[2]]; return p.apply(this, a); };
      }
    });
    await page.waitForTimeout(300);
    const idle = await page.evaluate(() => window.__since);
    await post(page, { type: "jarvis-hud-face", state: "approval" });
    await page.waitForTimeout(200);
    await page.evaluate(() => window.__faceSwitch.to("monkey"));
    await page.waitForFunction(() => window.__since && window.__since[0] === "monkey", null, { timeout: 30000 });
    const approval = await page.evaluate(() => window.__since);
    await done();
    assert.equal(idle[1], "idle");
    assert.ok(idle[2] < 5, `rested ${idle[2]} s the moment it opened`);
    assert.equal(approval[1], "approval");
    assert.ok(approval[2] > 1e8, `opened into waiting on you ${approval[2]} s after a change - an arrival reaction`);
  });

  await check("waiting on you, a face switch is only the cross-fade", async () => {
    const { page, done } = await open("redpanda");
    await post(page, { type: "jarvis-hud-face", state: "approval" });
    await page.waitForTimeout(300);
    await page.evaluate(() => window.__faceSwitch.to("seaotter"));
    await page.waitForTimeout(500);
    const mid = await page.evaluate(() => window.__faceSwitch.now());
    const o = await opts(page);
    await done();
    assert.equal(mid.face, "redpanda");
    assert.ok(o.goodbye > 0.2 && o.goodbye < 0.9, `goodbye ${o.goodbye}`);
    assert.ok(+mid.opacity < 0.85 && +mid.opacity > 0.05, `cross-fade ${mid.opacity}`);
  });

  await check("seasonal touches never show under Still while the stored options are still loading", async () => {
    const ctx = await browser.newContext({ viewport: { width: 300, height: 300 } });
    const page = await ctx.newPage();
    await page.addInitScript(() => localStorage.setItem("jarvis.animal.v1",
      JSON.stringify({ still: true, seasonal: true })));
    const read = await hold(page, "**/animal-shared.js");
    await page.goto(`${base}/faces.html?mode=display&feed=parent&face=redpanda`, { waitUntil: "commit" });
    await page.waitForFunction(() => window.__faceOpts, null, { timeout: 60000 });
    await page.waitForTimeout(600);
    await page.evaluate(() => {
      window.__seasonSeen = [];
      const tick = () => { const s = window.__faceSeason; if (s && "hide" in s) window.__seasonSeen.push(s.hide);
                           requestAnimationFrame(tick); };
      requestAnimationFrame(tick);
    });
    read.release();
    await page.waitForFunction(() => window.__faceOpts && window.__faceOpts.still === 1, null, { timeout: 30000 });
    // Enough frames to mean something, however slow the machine is.
    await page.waitForFunction(() => window.__seasonSeen.length > 8, null, { timeout: 30000 });
    const seen = await page.evaluate(() => window.__seasonSeen);
    await ctx.close();
    assert.ok(seen.length > 5, `frames seen: ${seen.length}`);
    assert.deepEqual(seen.filter((h) => h !== 1), [], "the touches eased away under Still instead of never showing");
  });

  await check("the frame pacer draws a stroke, a fact's nod and the focus stretch at the full rate - and no happening a focus session has taken away", async () => {
    const { page, done } = await open();
    await post(page, { type: "jarvis-hud-face", state: "idle" });
    await page.waitForTimeout(300);
    const at = (fn) => page.evaluate(fn);
    const busyNow = () => at(() => window.__faceSwitch.surface.view.busy);
    // Nothing playing: at rest (a happening may play by chance - look for a
    // clock with none).
    await at(() => {
      const s = window.__faceSwitch.surface, sp = CritterPose.species[s.theme.id];
      let t = Math.ceil(s.clock) + 10;
      while (sp.busy("idle", t) || sp.busy("idle", t + 2)) t += 0.5;
      s.clock = t;
    });
    await page.waitForTimeout(120);
    const rest = await busyNow();
    await post(page, { type: "jarvis-face-moment", kind: "fact" });
    await page.waitForTimeout(250);
    const nod = await busyNow();
    // A focus session on, then a clock where an idle happening would play.
    await post(page, { type: "jarvis-face-moment", kind: "focus", on: true });
    await page.waitForTimeout(1600);
    await at(() => {
      const s = window.__faceSwitch.surface, sp = CritterPose.species[s.theme.id];
      let t = Math.ceil(s.clock) + 10;
      while (!(sp.busy("idle", t) && sp.busy("idle", t + 1))) t += 0.25;
      s.clock = t;
    });
    await page.waitForTimeout(250);
    const focused = await busyNow();
    await post(page, { type: "jarvis-face-moment", kind: "focus", on: false });
    await page.waitForTimeout(250);
    const stretch = await busyNow();
    await done();
    assert.equal(rest, false, "at rest");
    assert.equal(nod, true, "a fact's nod");
    assert.equal(focused, false, "a happening a focus session has taken away");
    assert.equal(stretch, true, "the stretch as the session ends");
  });

  await check("a stroke across the Widget's face pets the animal, and it eases off", async () => {
    const { page, done } = await open();
    await page.mouse.move(100, 150);
    await page.mouse.down();
    for (let i = 0; i < 12; i++) { await page.mouse.move(100 + 8 * i, 150); await page.waitForTimeout(40); }
    const on = await opts(page);
    await page.mouse.up();
    await page.waitForTimeout(1400);
    const off = await opts(page);
    await done();
    assert.ok(on.pet > 0.5, `petting ${on.pet}`);
    assert.ok(on.petX > -1 && on.petX < 1);
    assert.equal(off.pet, 0);
  });

  await check("switching: a goodbye, the new face, then its hello - at full opacity", async () => {
    const { page, done } = await open();
    await page.waitForTimeout(300);
    await page.evaluate(() => window.__faceSwitch.to("pygmyowl"));
    await page.waitForTimeout(450);
    const mid = await page.evaluate(() => window.__faceSwitch.now());
    const o1 = await opts(page);
    // The hello's clock starts once the new face has been drawn once.
    // The snapshot is taken by the wait itself, at the moment it sees the hello
    // playing: looking a moment later can find it already over on a slow machine.
    const hello = await helloSeen(page);
    await page.waitForFunction(() => window.__faceSwitch.now().phase === null, null, { timeout: 30000 });
    const end = await page.evaluate(() => window.__faceSwitch.now());
    await done();
    assert.equal(mid.face, "redpanda");
    assert.ok(o1.goodbye > 0.2 && o1.goodbye < 0.9, `goodbye ${o1.goodbye}`);
    assert.equal(mid.opacity, "1");
    assert.equal(hello.face, "pygmyowl");
    assert.ok(hello.switching.hello >= 0 && hello.switching.hello <= 1);
    assert.equal(end.face, "pygmyowl");
    assert.equal(end.opacity, "1");
  });

  await check("the robot is fed like the animals, and switches with a goodbye and a hello", async () => {
    const { page, done } = await open("robot", { animal: { nods: false } });
    await page.waitForTimeout(400);
    const o = await opts(page);
    await page.evaluate(() => window.__faceSwitch.to("monkey"));
    await page.waitForTimeout(450);
    const o1 = await opts(page);
    const hello = await helloSeen(page);
    await done();
    assert.equal(o.variety, 1);
    assert.equal(o.nods, 0);
    assert.equal(o.petting, 1);
    assert.ok(o1.goodbye > 0.2 && o1.goodbye < 0.9, `the robot's goodbye ${o1.goodbye}`);
    assert.equal(hello.face, "monkey");
  });

  await check("under calm motion a character cross-fades; a face that is not one fades; two instruments switch at once", async () => {
    const calm = await open("redpanda", { reduced: true });
    await calm.page.evaluate(() => window.__faceSwitch.to("seaotter"));
    await calm.page.waitForTimeout(500);
    const faded = await calm.page.evaluate(() => window.__faceSwitch.now());
    await calm.done();
    assert.equal(faded.face, "redpanda");
    assert.ok(+faded.opacity < 0.8 && +faded.opacity > 0.1, `cross-fade ${faded.opacity}`);
    const inst = await open("redpanda");
    await inst.page.evaluate(() => window.__faceSwitch.to("arc"));
    await inst.page.waitForFunction(() => window.__faceSwitch.now().face === "arc", null, { timeout: 30000 });
    await inst.page.waitForTimeout(250);
    const arc = await inst.page.evaluate(() => window.__faceSwitch.now());
    await inst.page.waitForFunction(() => window.__faceSwitch.now().phase === null, null, { timeout: 30000 });
    await inst.page.evaluate(() => window.__faceSwitch.to("orbit"));
    const orbit = await inst.page.evaluate(() => window.__faceSwitch.now());
    await inst.done();
    assert.ok(+arc.opacity < 1, `arc fades in: ${arc.opacity}`);
    assert.equal(orbit.face, "orbit", "arc to orbit: at once");
    assert.equal(orbit.phase, null);
  });

  await check("the window's first appearance is worn at once; a later change plays the switch", async () => {
    const ctx = await browser.newContext({ viewport: { width: 300, height: 300 } });
    const page = await ctx.newPage();
    // The Widget's and the floating face's frame: no face in its address.
    await page.goto(`${base}/faces.html?mode=display&feed=parent`);
    await page.waitForFunction(() => window.__faceSwitch, null, { timeout: 60000 });
    await post(page, { type: "jarvis-hud-face", state: "idle", appearance: { face: "pygmyowl", bindings: {} } });
    await page.waitForTimeout(150);
    const first = await page.evaluate(() => window.__faceSwitch.now());
    await post(page, { type: "jarvis-hud-face", state: "idle", appearance: { face: "seaotter", bindings: {} } });
    await page.waitForTimeout(150);
    const later = await page.evaluate(() => window.__faceSwitch.now());
    await ctx.close();
    assert.equal(first.face, "pygmyowl");
    assert.equal(first.phase, null, "no goodbye for the default face the frame started on");
    assert.equal(later.face, "pygmyowl");
    assert.equal(later.phase, "bye", "the owl says goodbye before the otter comes");
  });

  await check("the frame pacer counts a cute moment as busy", async () => {
    const { page, done } = await open();
    await post(page, { type: "jarvis-hud-face", state: "idle" });
    await page.waitForTimeout(300);
    const r = await page.evaluate(() => {
      const s = window.__faceSwitch.surface, sp = CritterPose.species[s.theme.id];
      const m = s.theme.mem.get(s.view);
      // Idle, and rested, for 1000 s (born then too: a face rests only from
      // when it opened).
      m.at = m.born = performance.now() / 1000 - 1000;
      for (let t = Math.ceil(s.clock) + 200; t < s.clock + 3000; t += 0.25) {
        if (sp.busy("idle", t, 1000, m.opts) && !sp.busy("idle", t)) { s.clock = t + 1; return true; }
      }
      return false;
    });
    await page.waitForTimeout(300);
    const busy = await page.evaluate(() => window.__faceSwitch.surface.view.busy);
    await done();
    assert.ok(r, "found a cute moment");
    assert.equal(busy, true);
  });

  await check("attention: as it was for five minutes, then the happenings thin out; a pointer on the face or using Jarvis brings them back", async () => {
    const { page, done } = await open();
    await post(page, { type: "jarvis-hud-face", state: "idle" });
    await page.waitForTimeout(500);
    const fresh = await opts(page);
    assert.equal(fresh.attention, 1, "a page that has only just opened counts as used");
    // Each step waits for what it expects to see, not for a number of seconds:
    // a slow machine draws few frames, and the value only moves when one is drawn.
    const attnWhen = async (page, test) => (await page.waitForFunction(test, null, { timeout: 60000 })).jsonValue();
    // Six minutes on with nothing happening (LAST_ACTIVE is the page's own memory of when it last was).
    await page.evaluate(() => { LAST_ACTIVE -= 360; });
    // It starts to ease: the first value below 1 is part way down, never a snap to 0.
    const easing = { attention: await attnWhen(page, () => { const a = window.__faceOpts && window.__faceOpts.attention; return a < 1 ? a : false; }) };
    assert.ok(easing.attention < 1 && easing.attention > 0, `eased, not snapped: ${easing.attention}`);
    await attnWhen(page, () => window.__faceOpts && window.__faceOpts.attention === 0 ? true : false);
    const idle = await opts(page);
    assert.equal(idle.attention, 0);
    await page.evaluate(() => { POINTER_ON = true; });
    await attnWhen(page, () => window.__faceOpts && window.__faceOpts.attention === 1 ? true : false);
    const pointed = await opts(page);
    await page.evaluate(() => { POINTER_ON = false; });
    await attnWhen(page, () => window.__faceOpts && window.__faceOpts.attention === 0 ? true : false);
    const gone = await opts(page);
    // Using Jarvis (a question being asked) counts, and stays for five minutes.
    await post(page, { type: "jarvis-hud-face", state: "listening" });
    await attnWhen(page, () => window.__faceOpts && window.__faceOpts.attention === 1 ? true : false);
    await post(page, { type: "jarvis-hud-face", state: "idle" });
    await page.waitForTimeout(300);
    const used = await opts(page);
    await done();
    assert.equal(pointed.attention, 1);
    assert.equal(gone.attention, 0);
    assert.equal(used.attention, 1);
  });

  await check("a clip's phrase ends are handed to the pose ahead of time, and the finder that listens to the level stays out of it", async () => {
    const { page, done } = await open();
    await page.evaluate(() => { CritterPose.species.redpanda.gesturing = () => false; });
    await post(page, { type: "jarvis-hud-face", state: "speaking" });
    await page.waitForTimeout(200);
    // A clip: sound 0-1.5 s, a pause, sound 1.8-4.0 s. Its ends: 1.5 and 4.0 (2 s apart or more).
    const cued = await page.evaluate(() => {
      const n = 500, level = new Float32Array(n), z = new Float32Array(n);
      for (let i = 0; i < n; i++) level[i] = (i < 150 || (i >= 180 && i < 400)) ? 0.5 : 0;
      const packed = JarvisLipSync.pack({ fps: 100, n, level, open: z, wide: z, round: z });
      window.__faceVoice.cue({ id: 901, n: 1, track: packed, t: 0, at: Date.now(), playing: true, rate: 1 });
      return JarvisLipSync.phraseEnds(JarvisLipSync.unpack(packed));
    });
    assert.equal(cued.length, 2);
    const seen = [];
    for (let i = 0; i < 170; i++) {
      const o = await opts(page);
      seen.push({ due: o.phraseDue, n: o.phraseN, end: o.phraseEnd });
      await page.waitForTimeout(30);
    }
    await done();
    const first = seen.find((x) => typeof x.due === "number");
    assert.ok(first, "an end was handed over ahead of time");
    assert.ok(first.due > 0.5 && first.due <= 0.95, `first seen ${first.due} s before its end`);
    assert.ok(seen.every((x) => typeof x.due !== "number" || x.end === undefined), "the finder is not asked while the clip's ends are handed over");
    assert.ok(seen.every((x) => x.end === undefined || x.end >= 1e8), "the finder never finds an end of its own while the clip's track is used");
    const ns = [...new Set(seen.map((x) => x.n))];
    assert.ok(ns.includes(1) && ns.includes(2), `both ends taken up: ${ns}`);
    assert.ok(seen.some((x) => x.due < 0), "the end is kept after it has passed, for its gesture");
  });

  await browser.close();
  close();
}

if (fails.length) {
  console.log(`\n${fails.length} failed`);
  process.exit(1);
}
console.log("\nall passed");
