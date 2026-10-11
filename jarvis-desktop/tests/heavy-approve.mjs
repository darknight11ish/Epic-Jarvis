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
import { HeavyGate, isHeavy, needsFullCard, MIN_DELAY_MS } from "../src/heavy-approve.js";

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

  /* ── needsFullCard: what the widget refuses to decide on two lines ─────── */

  await check("needsFullCard: only a card that stays local AND can be undone is decided in the widget", () => {
    assert.equal(needsFullCard({ risk: { reach: "local", reversible: "yes" } }), false);
  });

  await check("needsFullCard: something that leaves this PC needs the whole card", () => {
    assert.equal(needsFullCard({ risk: { reach: "outbound", reversible: "yes" } }), true);
    // An unknown reach is not "local": the only safe reading of a word this
    // app does not know is that the action may leave.
    assert.equal(needsFullCard({ risk: { reach: "somewhere", reversible: "yes" } }), true);
  });

  await check("needsFullCard: something that cannot simply be undone needs the whole card", () => {
    assert.equal(needsFullCard({ risk: { reach: "local", reversible: "no" } }), true);
    // "hard" is not "yes": the card's own line says it is hard to undo.
    assert.equal(needsFullCard({ risk: { reach: "local", reversible: "hard" } }), true);
  });

  await check("needsFullCard: a card the backend never classified needs the whole card (finding D1)", () => {
    // The bug: isHeavy() reads notice.weight, so no notice read as "normal"
    // and a 320x44 strip could approve it. Unclassified is not "safe".
    assert.equal(needsFullCard({ notice: null }), true);
    assert.equal(needsFullCard({ risk: null }), true);
    assert.equal(needsFullCard({ risk: {} }), true);
    assert.equal(needsFullCard({}), true);
    assert.equal(needsFullCard(null), true);
    // And the specific shape the audit named: no notice AND an outbound risk.
    assert.equal(needsFullCard({ notice: undefined, risk: { reach: "outbound", reversible: "no" } }), true);
    // The unclassified card is exactly the one isHeavy() calls normal - that
    // difference is the whole finding, so hold both readings together here.
    assert.equal(isHeavy({ notice: undefined, risk: { reach: "outbound", reversible: "no" } }), false);
  });

  await check("needsFullCard: a malformed risk is refused, never read as local-and-reversible", () => {
    assert.equal(needsFullCard({ risk: "local" }), true);
    assert.equal(needsFullCard({ risk: [] }), true);
    assert.equal(needsFullCard({ risk: { reach: "local" } }), true); // reversible missing
    assert.equal(needsFullCard({ risk: { reversible: "yes" } }), true); // reach missing
  });

  await check("CONTROL: a labelled heavy card is still heavy, and a labelled normal local card is not", () => {
    // The new gate must not have replaced the old one: `isHeavy` keeps its
    // meaning for the Jarvis bar's own delay-and-scroll gate.
    const heavyLocal = { notice: { weight: "heavy" }, risk: { reach: "local", reversible: "yes" } };
    assert.equal(isHeavy(heavyLocal), true);
    assert.equal(needsFullCard(heavyLocal), false, "needsFullCard answers the reach question only");
    const normalOutbound = { notice: { weight: "normal" }, risk: { reach: "outbound", reversible: "no" } };
    assert.equal(isHeavy(normalOutbound), false);
    assert.equal(needsFullCard(normalOutbound), true);
  });

  console.log(`\n${fails.length === 0 ? "ok" : "FAIL"}  ${fails.length} failing`);
  if (fails.length) process.exitCode = 1;
}

await main();
