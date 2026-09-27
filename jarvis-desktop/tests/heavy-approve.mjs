/**
 * "Slower Approve on risky cards" (feasibility I110): isHeavy() and
 * HeavyGate - both conditions (a fixed delay, and the card having been
 * scrolled into view) have to clear before Approve is allowed.
 *
 *     node tests/heavy-approve.mjs
 *
 * No browser: `scrollEl` is a plain mock object with the handful of
 * properties/methods HeavyGate actually reads (`scrollHeight`,
 * `clientHeight`, `scrollTop`, `addEventListener`, `removeEventListener`) -
 * exactly what a real element would offer, nothing DOM-specific about it.
 */
import assert from "node:assert/strict";
import { HeavyGate, isHeavy, MIN_DELAY_MS } from "../src/heavy-approve.js";

const fails = [];

/** Runs `fn` (which may be async) and records ok/FAIL, awaiting it so an
 * assertion inside an async check is actually caught. */
async function check(name, fn) {
  try {
    await fn();
    console.log(`ok    ${name}`);
  } catch (e) {
    fails.push(name);
    console.log(`FAIL  ${name}\n      ${e.stack || e.message}`);
  }
}

/** A stand-in scroll container. `scroll(top)` fires the listener the same
 * way a real "scroll" event would. */
function mockScrollEl({ scrollHeight, clientHeight, scrollTop = 0 }) {
  const listeners = [];
  return {
    scrollHeight,
    clientHeight,
    scrollTop,
    addEventListener(_type, fn) { listeners.push(fn); },
    removeEventListener(_type, fn) {
      const i = listeners.indexOf(fn);
      if (i >= 0) listeners.splice(i, 1);
    },
    scroll(top) {
      this.scrollTop = top;
      for (const fn of listeners.slice()) fn();
    },
    listenerCount() { return listeners.length; },
  };
}

const wait = (ms) => new Promise((r) => setTimeout(r, ms));

async function main() {
  await check("isHeavy: true only for notice.weight === \"heavy\"", () => {
    assert.equal(isHeavy({ notice: { weight: "heavy" } }), true);
    assert.equal(isHeavy({ notice: { weight: "normal" } }), false);
  });

  await check("isHeavy: no notice at all (an older backend) is treated as normal - stricter only", () => {
    assert.equal(isHeavy({ notice: null }), false);
    assert.equal(isHeavy({}), false);
    assert.equal(isHeavy(null), false);
  });

  await check("with no scrollEl, the scroll condition is satisfied immediately", () => {
    const g = new HeavyGate({ delayMs: 50 });
    g.start();
    assert.equal(g.scrollOk, true);
    assert.equal(g.timeOk, false);
    assert.equal(g.ok, false); // the delay has not elapsed yet
    g.stop();
  });

  await check("content that already fits needs no scrolling", async () => {
    const el = mockScrollEl({ scrollHeight: 100, clientHeight: 300 }); // fits
    const g = new HeavyGate({ scrollEl: el, delayMs: 10 });
    let changed = 0;
    g.onChange = () => changed++;
    g.start();
    // start() measures via requestAnimationFrame - give the event loop a turn.
    await wait(0);
    assert.equal(g.scrollOk, true);
    await wait(30);
    assert.equal(g.timeOk, true);
    assert.equal(g.ok, true);
    assert.ok(changed >= 1, "onChange should have fired at least once");
    g.stop();
  });

  await check("content taller than the container needs an actual scroll to the bottom", async () => {
    const el = mockScrollEl({ scrollHeight: 900, clientHeight: 300, scrollTop: 0 });
    const g = new HeavyGate({ scrollEl: el, delayMs: 5 });
    g.start();
    await wait(0);
    assert.equal(g.scrollOk, false, "has not scrolled yet");
    await wait(20);
    assert.equal(g.timeOk, true, "the delay alone elapsed");
    assert.equal(g.ok, false, "but the scroll condition has not, so Approve stays grey");
    el.scroll(300); // partway, not yet at the bottom
    assert.equal(g.scrollOk, false);
    assert.equal(g.ok, false);
    el.scroll(600); // the bottom (900 - 300 = 600, the maximum scrollTop)
    assert.equal(g.scrollOk, true);
    assert.equal(g.ok, true, "both conditions have now cleared");
    g.stop();
  });

  await check("once scrolled to the bottom, scrolling back up does not re-lock it", async () => {
    const el = mockScrollEl({ scrollHeight: 900, clientHeight: 300, scrollTop: 0 });
    const g = new HeavyGate({ scrollEl: el, delayMs: 0 });
    g.start();
    el.scroll(600);
    assert.equal(g.scrollOk, true);
    el.scroll(0); // back to the top
    assert.equal(g.scrollOk, true, "having been seen once is enough - never re-locks");
    g.stop();
  });

  await check("start() on a genuinely new card resets both conditions", async () => {
    const el = mockScrollEl({ scrollHeight: 900, clientHeight: 300, scrollTop: 0 });
    const g = new HeavyGate({ scrollEl: el, delayMs: 0 });
    g.start();
    el.scroll(600);
    await wait(5);
    assert.equal(g.ok, true);
    // A different card arrives - start() again, same instance (the real
    // callers keep one HeavyGate for the life of the window).
    el.scrollTop = 0;
    g.start();
    assert.equal(g.timeOk, false);
    assert.equal(g.scrollOk, false, "a fresh card must be scrolled again, even on the same element");
    g.stop();
  });

  await check("stop() removes the scroll listener so a closed card cannot flip a later one's state", () => {
    const el = mockScrollEl({ scrollHeight: 900, clientHeight: 300 });
    const g = new HeavyGate({ scrollEl: el, delayMs: 1000 });
    g.start();
    assert.equal(el.listenerCount(), 1);
    g.stop();
    assert.equal(el.listenerCount(), 0);
  });

  await check("secondsLeft counts down to 0 and never goes negative", async () => {
    const g = new HeavyGate({ delayMs: 30 });
    assert.equal(g.secondsLeft(), Math.ceil(30 / 1000));
    g.start();
    assert.ok(g.secondsLeft() >= 0);
    await wait(50);
    assert.equal(g.secondsLeft(), 0);
    g.stop();
  });

  await check("the exported default delay is a real number of milliseconds, at least a second", () => {
    assert.ok(Number.isFinite(MIN_DELAY_MS) && MIN_DELAY_MS >= 1000, MIN_DELAY_MS);
  });

  console.log(`\n${fails.length === 0 ? "ok" : "FAIL"}  ${fails.length} failing`);
  if (fails.length) process.exitCode = 1;
}

await main();
