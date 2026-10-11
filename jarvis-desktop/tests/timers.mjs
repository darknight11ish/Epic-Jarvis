/**
 * The two timers the 2026-10-08 cohesion audit found (finding 2), and the
 * waits the app now asks for instead.
 *
 * WHAT IS PINNED, and why this way. The bug was a flat `setInterval(..., 1000)`
 * in `main.js` (the Jarvis bar) and `widget.js` (the widget window): 60 calls a
 * minute to repaint one line, whether or not a card was on screen and whether
 * or not anybody was looking at the window. A test that merely watched the
 * countdown text would pass just as happily with the old timer, so the check
 * is on the WAITS the app asks for, measured through the real pages:
 *
 *   `src-old` (the HEAD files) asks for 1000 ms, always -> 60 a minute.
 *   `src` (this change) asks for the rest of the idle minute when there is
 *   nothing to show, and only the remainder of the second being shown when a
 *   card's clock is running.
 *
 * The pages are served on a real socket and loaded in Chromium (the harness
 * `uikit.mjs` every other rendering suite uses), and Playwright's fake clock
 * steps the minute - the same `page.clock` `youtube.mjs` already uses. The
 * count comes from the asked-for waits, not from how many times they fired:
 * `runFor` yields a real macrotask per timer callback, so a fire count would
 * measure the harness as much as the app (measured 2026-10-08: a per-second
 * interval showed 31 wakes in 120 steps).
 *
 * Numbers, one simulated minute (2026-10-08):
 *
 *   Jarvis bar, no card        before 60  ->  after 0
 *   widget, no card            before 60  ->  after 0
 *   Jarvis bar, card counting down   before 60 -> after 0 own wakes
 *   widget, card counting down       before 60 -> after 0 own wakes
 *   the same, window hidden          before 60 -> after 0
 *
 * "0" is not "the clock stopped": the same runs show the text moving by
 * exactly one minute (`59:00 left to decide` -> `58:00`), and the waits asked
 * for are 60,9xx ms idle and ~1,000 ms while a card counts down.
 */
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, join, resolve } from "node:path";
import * as K from "./uikit.mjs";

const HERE = dirname(fileURLToPath(import.meta.url));
const read = (p) => readFileSync(join(HERE, "..", p), "utf8");
const fails = [];
const check = async (name, fn) => {
  try { await fn(); console.log(`ok    ${name}`); }
  catch (e) { fails.push(name); console.log(`FAIL  ${name}\n      ${e.message}`); }
};

const NOW = 1_700_000_000_000;
const APPROVAL = {
  id: "a1", action: "switch_model", tier: "ask", created: 1,
  detail: JSON.stringify({ ref: "qwen3:8b" }), prompt: "Switch the active model?",
  risk: { reversible: "yes", reach: "local", swipe_ok: true, why: "", classified: true },
  raised: null, expires_in: 3600,
  notice: { title: "Switch the model", weight: "normal", deny_ok: true, approve_ok: false,
            body: "Nothing has happened yet." },
};

/* ── Without a page: the helper the two surfaces now share ─────────────── */

const clock = await import("../src/clock-timer.js");
const pairPoll = await import("../src/devices-pair-poll.js");

await check("the idle wait is a minute, and a shown clock's wait is the second it shows", async () => {
  // A minute is the slow cadence the rest of the app's panels use; the clock
  // itself changes every second it is on screen (expiryWords prints M:SS), so
  // the audit's "changes 60 times an hour" does not describe this clock. The
  // alignment is what makes the digits turn over ON the second.
  assert.equal(clock.IDLE_MS, 60000);
  assert.equal(clock.alignMs(0), 1000);
  assert.equal(clock.alignMs(1), 999);
  assert.equal(clock.alignMs(999), 1);
  assert.equal(clock.alignMs(1000), 1000);
  // Without a delay() it must refuse to run rather than spin on a guess.
  assert.throws(() => clock.clockTimer(() => {}), /needs delay/);
});

await check("a wake with nothing to show paints nothing, and asks for the idle minute", async () => {
  // The tick is driven through the helper's own injection points, and the
  // injected scheduler keeps the callback instead of running it, so nothing
  // can fire behind the assertions.
  let paints = 0;
  let show = false;
  let hidden = false;
  let pending = null;
  const asked = [];
  const t = clock.clockTimer(() => { paints += 1; }, {
    delay: () => (show ? 1000 : clock.IDLE_MS),
    hidden: () => hidden,
    schedule: (fn, ms) => { asked.push(ms); pending = fn; return asked.length; },
    cancel: () => { pending = null; },
    now: () => 500,
  });
  t.wake();
  assert.equal(paints, 1, "the first wake paints the line it was started for");
  assert.equal(asked.length, 1);
  assert.equal(asked[0], clock.IDLE_MS + 500,
    `the idle wait is the shown minute plus the alignment, was ${asked[0]} ms`);
  // An idle wake: it re-reads the wait and arms the idle minute again, and
  // does not paint - the wait it just ran was an idle one, so the line it
  // showed cannot have changed. The old flat interval did this 60 times a
  // minute.
  const before = paints;
  const idle = pending;
  idle();
  assert.equal(paints, before, `an idle wake repainted ${paints - before} times`);
  assert.equal(asked.length, 2);
  assert.equal(asked[1], clock.IDLE_MS + 500, `second idle wait was ${asked[1]}`);
  // A card arrives: the next wait is the second being shown, aligned on top,
  // and the wake after a second-level wait repaints.
  show = true;
  t.wake();
  assert.equal(paints, before + 1);
  assert.equal(asked[2], 1500, `a shown clock asked for ${asked[2]} ms`);
  pending();
  assert.equal(paints, before + 2, "a wake after a second-level wait repaints");
  assert.equal(asked.length, 4);
  assert.equal(asked[3], 1500);
  // Hidden: the pending wake is dropped and the line paints nothing, but the
  // timer still arms the idle beat so it can notice being shown again.
  const armedAt = asked.length;
  hidden = true;
  t.wake();
  assert.equal(paints, before + 2, "a hidden window paints nothing");
  assert.equal(asked.length, armedAt + 1, "a hidden window sleeps the idle minute");
  assert.equal(asked[asked.length - 1], clock.IDLE_MS);
  // Shown again: one paint at once, and back to the second-level wait.
  hidden = false;
  t.wake();
  assert.equal(paints, before + 3);
  assert.equal(asked.length, armedAt + 2);
  assert.equal(asked[asked.length - 1], 1500);
  t.stop();
  t.wake();
  assert.equal(paints, before + 3, "wake() after stop() must do nothing");
  assert.equal(asked.length, armedAt + 2);
});

await check("a hidden window stops the clock, and coming back restarts it", async () => {
  let paints = 0;
  let hidden = false;
  let armed = 0;
  let cancelled = 0;
  let onShown = null;      // what `visibility` was handed
  let tick = null;         // what `schedule` was handed - a different function
  const waits = [];
  const t = clock.clockTimer(() => { paints += 1; }, {
    delay: () => 1000,
    hidden: () => hidden,
    schedule: (fn, ms) => { armed += 1; waits.push(ms); tick = fn; return armed; },
    cancel: () => { cancelled += 1; },
    now: () => 600,
    visibility: (fn) => { onShown = fn; return () => { onShown = null; }; },
  });
  t.wake();
  assert.equal(paints, 1);
  assert.equal(waits[0], 1400, `first wait was ${waits[0]} ms (1000 + the 400 left of the second)`);
  // Hidden: the armed wake is dropped and the timer asks for nothing.
  hidden = true;
  onShown();
  assert.equal(cancelled, 1, "the armed wake must be cancelled when the window goes out of sight");
  assert.equal(armed, 1, "a hidden window must not arm a new wake");
  assert.equal(paints, 1, "and must not paint");
  // A wake of its own while hidden - were one still armed - holds the slow
  // beat and paints nothing. This is the wake the hide just dropped, which is
  // why the timer cannot come back on its own: only the next visibility
  // change restarts it.
  t.wake();
  assert.equal(paints, 1);
  assert.equal(armed, 2);
  assert.equal(waits[1], clock.IDLE_MS, "a hidden window sleeps the idle minute");
  assert.equal(typeof tick, "function");
  // Shown again with nothing armed (the hide dropped it): one paint at once,
  // because the countdown moved while the window was away.
  hidden = true;
  onShown();                       // hidden again: drops the wake t.wake() armed
  assert.equal(paints, 1);
  assert.equal(cancelled, 2);
  hidden = false;
  onShown();                       // shown, nothing armed: paint and re-arm
  assert.equal(paints, 2, "coming back paints once");
  assert.equal(armed, 3);
  assert.equal(waits[2], 1400, "and resumes the second-level wait");
  // A second "shown" with a wake already armed changes nothing.
  onShown();
  assert.equal(paints, 2);
  assert.equal(armed, 3);
  t.stop();
  assert.equal(onShown, null, "stop() unsubscribes");
});
/* ── The pairing poll's cadence, as a decision ─────────────────────────── */

await check("the pairing poll is fast while a code is new, then the app's slow cadence", async () => {
  // The device LIST is not polled at all - a `devices` event re-reads it (the
  // check below). This timer carries the pairing panel, where the four words
  // arrive with the phone's claim and the backend publishes no event for it
  // (`backend/jarvis_devices.py`: `_publish("devices", ...)` fires on a
  // registry change, and `claim()` only `_audit`s). So the first minute keeps
  // the old 2 s - the QR moment - and the wait backs off after it.
  assert.equal(pairPoll.POLL_MS_HOT, 2000);
  assert.equal(pairPoll.POLL_MS_COOL, 15000, "the cadence brain.js polls its own panels at");
  assert.equal(pairPoll.HOT_WINDOW_MS, 60000);
  const t0 = 1_700_000_000_000;
  assert.equal(pairPoll.pairWaitMs(t0, t0), 2000);
  assert.equal(pairPoll.pairWaitMs(t0, t0 + 59_999), 2000);
  assert.equal(pairPoll.pairWaitMs(t0, t0 + 60_000), 15000);
  assert.equal(pairPoll.pairWaitMs(t0, t0 + 10 * 60_000), 15000);
  // A session the page has just learned about (a reloaded window) must not
  // wait fifteen seconds for its first words.
  assert.equal(pairPoll.pairWaitMs(0, t0), 2000);
  assert.equal(pairPoll.pairWaitMs(NaN, t0), 2000);
  assert.equal(pairPoll.pairWaitMs(undefined, t0), 2000);
});

await check("the source no longer carries either flat one-second timer", async () => {
  for (const file of ["main.js", "widget.js"]) {
    const src = read(`src/${file}`);
    assert.ok(!/setInterval\(\(\)\s*=>\s*\{\s*if \(state\.approval/.test(src),
      `${file} still has the flat one-second approval-clock interval`);
    assert.match(src, /clockTimer\(/, `${file} must build its clock from clock-timer.js`);
    assert.match(src, /nudgeApprovalClock\(\)/,
      `${file} must wake the clock when a card opens or closes`);
  }
  const devices = read("src/devices.js");
  assert.ok(!/setInterval\(poll, POLL_MS\)/.test(devices),
    "devices.js still has the flat 2 s pairing poll");
  assert.ok(!/\bPOLL_MS\b\s*=\s*2000/.test(devices), "the old POLL_MS constant is back");
  assert.match(devices, /pairWaitMs\(codeShownAt/, "the wait must come from the session's age");
});

/* ── The two real pages, stepped a minute of fake time ─────────────────── */

/** Watches the scheduling calls, so the test can read the waits the app asks for. */
function watchWaits(keys) {
  window.__asked = [];
  const realSetTimeout = window.setTimeout;
  const realSetInterval = window.setInterval;
  const hit = (fn) => keys.find((k) => String(fn).includes(k));
  const wrap = (fn) => { const k = hit(fn); return k ? function (...a) { return fn.apply(this, a); } : fn; };
  window.setTimeout = function (fn, ms, ...a) {
    const w = wrap(fn);
    if (w !== fn) window.__asked.push({ kind: "timeout", ms });
    return realSetTimeout.call(this, w, ms, ...a);
  };
  window.setInterval = function (fn, ms, ...a) {
    const w = wrap(fn);
    if (w !== fn) window.__asked.push({ kind: "interval", ms });
    return realSetInterval.call(this, w, ms, ...a);
  };
}

/** Calls the app's own timer would make in `windowMs`, from the waits asked for. */
function wakeUps(asked, windowMs) {
  let n = 0;
  for (const a of asked) {
    if (a.kind === "interval") n += a.ms > 0 ? Math.floor(windowMs / a.ms) : windowMs;
  }
  let sum = 0;
  for (const a of asked) {
    if (a.kind !== "timeout") continue;
    sum += Math.max(a.ms, 1);
    if (sum > windowMs) break;
    n += 1;
  }
  return n;
}

const { base, close } = await K.serve();
const browser = await K.launch();

async function aMinute(file, data, viewport, { hidden = false } = {}) {
  const page = await K.open(browser, base, file, data, viewport);
  // The fake clock has to own the document's timers from before the app's
  // scripts arm them, so it is installed and the page reloaded.
  await page.clock.install({ time: new Date(NOW) });
  await page.addInitScript(watchWaits, ["isHidden()) return arm()"]);
  await page.reload();
  await page.waitForTimeout(700);
  await page.clock.pauseAt(new Date(await page.evaluate(() => Date.now() + 500)));
  if (hidden) {
    await page.evaluate(() => {
      Object.defineProperty(document, "hidden", { configurable: true, get: () => true });
      Object.defineProperty(document, "visibilityState", { configurable: true, get: () => "hidden" });
      document.dispatchEvent(new Event("visibilitychange"));
    });
  }
  for (let i = 0; i < 60; i++) {
    await page.clock.runFor(1000);
    await page.waitForTimeout(2);
  }
  const asked = await page.evaluate(() => window.__asked);
  const text = await page.evaluate(() => {
    const line = document.querySelector("#approval .approval-reassure")
      || document.getElementById("appr-risk");
    return line ? line.textContent : null;
  });
  await page.close();
  return { asked, wakes: wakeUps(asked, 60_000), text };
}

await check("the Jarvis bar's clock: 60 wakes a minute becomes none when there is no card", async () => {
  const none = await aMinute("index.html", { pending: [] }, { width: 760, height: 1600 });
  assert.ok(none.asked.length > 0, "the clock's timer was never armed");
  assert.equal(none.wakes, 0,
    `the bar's clock made ${none.wakes} wake-ups in a minute with nothing to show`);
  for (const a of none.asked) {
    assert.ok(a.ms >= 60_000, `an idle wait of ${a.ms} ms is not the idle minute`);
  }
  assert.match(none.text, /^Nothing runs until you decide\./);
});

await check("the widget's clock: 60 wakes a minute becomes none when there is no card", async () => {
  const none = await aMinute("widget.html", { pending: [] }, { width: 320, height: 520 });
  assert.ok(none.asked.length > 0, "the clock's timer was never armed");
  assert.equal(none.wakes, 0,
    `the widget's clock made ${none.wakes} wake-ups in a minute with nothing to show`);
  for (const a of none.asked) {
    assert.ok(a.ms >= 60_000, `an idle wait of ${a.ms} ms is not the idle minute`);
  }
});

await check("with a card counting down the line keeps its countdown", async () => {
  const shown = await aMinute("index.html", { pending: [APPROVAL] }, { width: 760, height: 1600 });
  // The countdown is on screen. The fix changes how often the timer wakes,
  // never what the owner reads - the same shape the old line had.
  const m = /(\d+):(\d\d) left to decide/.exec(shown.text || "");
  assert.ok(m, `no countdown on the line: ${shown.text}`);
  const left = Number(m[1]) * 60 + Number(m[2]);
  assert.ok(left > 0 && left <= 60 * 60, `an odd countdown: "${m[0]}"`);
  // And every wait it asked for is one the display can use. The very first is
  // the idle minute - the clock arms at page load, before the card reaches the
  // page - and after that the second being shown, or the queue's own ~2 s
  // repaint. Never a sub-second spin, and never a wait longer than a minute.
  assert.ok(shown.asked.length > 0, "the clock was never armed with a card up");
  assert.ok(shown.asked[0].ms >= 60_000,
    `the arm at page load is the idle one, was ${shown.asked[0].ms} ms`);
  for (const [i, a] of shown.asked.entries()) {
    assert.ok(a.ms >= 900 && a.ms <= 61_000, `wait ${i} was ${a.ms} ms`);
  }
});

await check("a hidden window makes no clock wake-ups at all", async () => {
  const hidden = await aMinute("index.html", { pending: [APPROVAL] }, { width: 760, height: 1600 },
    { hidden: true });
  const hiddenAsked = hidden.asked.filter((a) => a.ms < 60_000);
  assert.deepEqual(hiddenAsked, [],
    `a hidden window still asked for ${hiddenAsked.length} second-level wake-ups`);
  assert.equal(hidden.wakes, 0);
});

await browser.close();
close();

if (fails.length) {
  console.log(`\n${fails.length} failed: ${fails.join("; ")}`);
  process.exit(1);
}
console.log("\nClock timers hold");
