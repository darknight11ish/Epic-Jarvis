/**
 * settings-live.js - the ONE refresh rule for a Settings row whose state
 * something other than this page can change (2026-11-19 state-drift.
 *
 *   node tests/settings-live.mjs
 *
 * WHY THIS EXISTS. DESKTOP-STATE-DRIFT found a class, not a row: a control
 * paints what the PC said once and then never asks again, while a chat
 * sentence, another window or a late answer to ONE approval card moves the
 * real value. This suite proves the shared rule the fixed rows now use:
 *
 *   1. it reads once when a row is constructed (the page's first paint);
 *   2. it reads AGAIN on demand (`soon`) - the trigger the approval queue, the
 *      PC's own event and the window coming back into view all call;
 *   3. after a carded save ends before the card was answered, `hold()` makes it
 *      keep re-reading at the pending rate until `release()` - so a card
 *      answered 30 seconds late still repaints the row;
 *   4. `pending()` stops being true at the gate's own limit, so an unconfirmed
 *      tick cannot be drawn as unconfirmed forever;
 *   5. a "took too long" bridge error is recognised, so a card still waiting is
 *      never shown as a failed save.
 *
 * Run by CI's frontend shards (`tests/*.mjs`); needs no browser.
 */
import assert from "node:assert/strict";
import { test } from "node:test";

import { liveRow, looksLikeATimeout, TIMING } from "../src/settings-live.js";

const tick = (ms = 0) => new Promise((resolve) => setTimeout(resolve, ms));

/** A read that counts its calls and can be told to fail once. */
function counter({ failFirst = false } = {}) {
  const seen = { calls: 0, failures: 0 };
  const read = async () => {
    seen.calls += 1;
    if (failFirst && seen.calls === 1) {
      seen.failures += 1;
      throw new Error("the PC did not answer");
    }
  };
  return { seen, read };
}

test("the rule's numbers are in one place and are the gate's own window", () => {
  // jarvis_gate.py APPROVAL_TIMEOUT is 900 s; the rule allows two minutes of
  // slack after it so an expired card reads as settled, not as still waiting.
  assert.equal(TIMING.steadyMs, 20000);
  assert.equal(TIMING.pendingMs, 3000);
  assert.equal(TIMING.pendingCapMs, 900000 + 120000);
});

test("a constructed row reads ONCE - its first paint comes through the same path as every later one", async () => {
  const { seen, read } = counter();
  const live = liveRow({ read, queue: false, visible: false, steadyMs: 60_000 });
  try {
    await tick();
    assert.equal(seen.calls, 1, "the row did not read on construction");
    assert.equal(live.pending(), false, "a fresh row is not waiting on a card");
  } finally {
    live.stop();
  }
});

test("soon() re-reads - this is what the approval queue, the PC's own event and the window returning all call", async () => {
  const { seen, read } = counter();
  const live = liveRow({ read, queue: false, visible: false, steadyMs: 60_000 });
  try {
    await tick();
    live.soon();
    await tick();
    assert.equal(seen.calls, 2, "a queue/event/visibility trigger did not re-read");
  } finally {
    live.stop();
  }
});

test("a carded save that ends before the card is answered keeps re-reading until the answer arrives", async () => {
  const { seen, read } = counter();
  const live = liveRow({
    read, queue: false, visible: false,
    steadyMs: 60_000, pendingMs: 15, pendingCapMs: 60_000,
  });
  try {
    await tick();
    assert.equal(seen.calls, 1);
    // The Rust call gave up after its 20 s while the card's own 900 s window is
    // still open: hold() starts the 3 s (here 15 ms) waiting poll.
    live.hold();
    assert.equal(live.pending(), true, "hold() did not mark the card as waiting");
    await tick(70);
    assert.ok(seen.calls >= 3, `the row stopped re-reading while the card waited (${seen.calls} reads)`);
    // The card is answered: the row releases back to the steady rate.
    live.release();
    const callsAtRelease = seen.calls;
    assert.equal(live.pending(), false, "release() did not clear the waiting state");
    await tick(70);
    assert.equal(seen.calls, callsAtRelease, "the row kept the waiting rate after release()");
  } finally {
    live.stop();
  }
});

test("the waiting poll stops on its own at the gate's own limit - an unconfirmed tick is not forever", async () => {
  const { seen, read } = counter();
  const live = liveRow({
    read, queue: false, visible: false,
    steadyMs: 60_000, pendingMs: 10, pendingCapMs: 40,
  });
  try {
    await tick();
    live.hold();
    assert.equal(live.pending(), true);
    await tick(120);
    assert.equal(live.pending(), false, "the pending window never closed, so the row would stay unconfirmed forever");
    assert.ok(seen.calls >= 3, "the row did not read while the card's window was open");
  } finally {
    live.stop();
  }
});

test("a read that throws does not stop the rule; the row paints its own failure words", async () => {
  const { seen, read } = counter({ failFirst: true });
  const live = liveRow({
    read, queue: false, visible: false,
    steadyMs: 15, pendingMs: 15, pendingCapMs: 60_000,
  });
  try {
    await tick(60);
    assert.ok(seen.calls >= 2, "the first read failed and the poll never ran again");
    assert.equal(seen.failures, 1);
  } finally {
    live.stop();
  }
});

test("the bridge's 'took too long' is recognised, and a real refusal is not", () => {
  // plain_errors.rs's own words for the 20 s call timing out while its card is
  // still live - the exact case never put on screen as a failed save.
  assert.equal(looksLikeATimeout(new Error("Jarvis took too long to answer. Try again in a moment.")), true);
  assert.equal(looksLikeATimeout(new Error("timed out")), true);
  assert.equal(looksLikeATimeout(new Error("timeout while waiting")), true);
  assert.equal(looksLikeATimeout(new Error("The PC refused to save that switch.")), false);
  assert.equal(looksLikeATimeout(null), false);
});
