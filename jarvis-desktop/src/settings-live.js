/**
 * settings-live.js - ONE refresh rule for a Settings row whose state something
 * other than this page can change.
 *
 * WHY THIS EXISTS. The 2026-11-19 desktop settings audit (DESKTOP-STATE-DRIFT)
 * found a class, not a row: a control paints what the PC said once, and then
 * never asks again, while a chat sentence, another window or a late answer to
 * ONE approval card moves the real value. The owner's measured Wi-Fi row is the
 * template (the line said the reconnect was on over an unticked box); hands-free
 * mode had the identical shape - its Rust command gives up after 20 s while the
 * approval card it raised waits up to 15 minutes (`jarvis_gate.py`
 * APPROVAL_TIMEOUT = 900 s), and nothing re-read after the card was answered.
 *
 * "Read replies out loud" (PC-owned, chat writes the same value) and "Say One
 * moment" (the behaviour ANDs this page's localStorage with the PC's
 * voice-flow.json) went stale the same way.
 *
 * THE RULE, in one sentence: **a row painted from a state another writer can
 * change re-reads that state when the window comes back into view, when the
 * approval queue changes, when that state's own event kind arrives, and on a
 * bounded steady poll while the page is visible; and after a save that may
 * still be waiting on a card it re-reads every 3 s until the PC answers or the
 * gate's own 15-minute window closes.**
 *
 * That is the whole rule and it is stated once, here. A row either uses it or
 * the Tier-1 contract test (`tests/settings-state-contract.mjs` - one table of
 * every state-bearing row and the mechanism that keeps it true) says why not.
 * The behaviour suites (`tests/settings-live.mjs`, `tests/read-aloud-settings.mjs`,
 * `tests/handsfree-late-card.mjs`, `tests/voice-one-moment.mjs`,
 * `tests/settings-supervise.mjs`) drive the real modules over fake DOMs.
 *
 * WHAT IT IS NOT. It never writes and never decides an approval: `read` is a
 * read, and a card is still answered by a person through `/api/approve`. It
 * never paints; the row's own `read` paints, from the PC's answer, exactly as
 * it does today - this module only decides WHEN to ask again. A read that fails
 * is painted by the row's own `read` (an unreadable state is never "off").
 *
 * A SKIP IS NEVER A PASS. There is no silent give-up here: the steady poll and
 * the bounded waiting poll always end on a real read of the PC, so the last
 * thing on screen is what the PC said, never what this page hoped.
 *
 * @module settings-live
 */

import { onEvent, onQueue } from "./jarvis-link.js";

/**
 * The rule's numbers, in ONE place.
 *
 * `steadyMs`   - a visible page re-reads a PC-owned row at least this often.
 * `pendingMs`  - while a card may still be waiting, this often.
 * `pendingCapMs` - and for at most this long: the gate's own 15-minute
 *                  APPROVAL_TIMEOUT (`jarvis_gate.py:66-67`, 900 s) plus two
 *                  minutes of slack, after which the card has expired and the
 *                  PC's answer is final.
 *
 * Tests shorten these to milliseconds; nothing in the product changes them.
 */
export const TIMING = Object.freeze({
  steadyMs: 20000,
  pendingMs: 3000,
  pendingCapMs: 900000 + 120000,
});

/** Whether an error is the bridge's "took too long" for a call that may still
 *  be waiting on a card. The words are `plain_errors.rs`'s own (`timeout`). */
export function looksLikeATimeout(error) {
  const said = String((error && error.message) || error || "");
  return /took too long|timed out|timeout/i.test(said);
}

/**
 * Keeps one Settings row fresh with the rule above.
 *
 * @param {object} options
 * @param {() => Promise<void>} options.read - re-reads the PC and repaints the
 *   row. Called once at construction (the page's first paint) and again on
 *   every trigger below. It must paint its own failure words.
 * @param {string[]|null} [options.kinds] - the bus event kinds that mean THIS
 *   state moved (`wifi_reconnect`, `read_aloud`, ...). `null` means the state
 *   publishes no event of its own; the queue and the poll still cover it.
 * @param {boolean} [options.queue] - re-read when the approval queue changes
 *   (a card appeared, was answered or expired). Default true.
 * @param {boolean} [options.visible] - re-read when the window comes back into
 *   view. Default true.
 * @returns {{soon: () => void, hold: (ms?: number) => void, release: () => void,
 *            pending: () => boolean, stop: () => void}}
 *   `hold()` starts the 3 s waiting poll (call it when a carded save's call
 *   ended before a person answered); `release()` ends it (the PC answered, or
 *   the row learned it never would). `pending()` is what the row's paint asks
 *   so an unconfirmed value is drawn as unconfirmed, never as current.
 */
export function liveRow({
  read,
  kinds = null,
  queue = true,
  visible = true,
  steadyMs = TIMING.steadyMs,
  pendingMs = TIMING.pendingMs,
  pendingCapMs = TIMING.pendingCapMs,
} = {}) {
  if (typeof read !== "function") {
    throw new TypeError("liveRow needs a read function");
  }
  const doc = typeof document !== "undefined" ? document : null;
  let timer = null;
  let soonTimer = null;
  let stopped = false;
  let running = false;
  let rerun = false;
  let pendingUntil = 0;

  const now = () => Date.now();
  const pending = () => pendingUntil > 0 && now() < pendingUntil;
  const shown = () => !doc || doc.hidden !== true;

  function clearTimer() {
    if (timer !== null) {
      clearTimeout(timer);
      timer = null;
    }
  }

  function arm(delay) {
    clearTimer();
    if (stopped || !shown() || !delay) return;
    timer = setTimeout(tick, delay);
    // A Settings window that shuts mid-wait must not keep the process awake;
    // in Node this is what lets a browser-free test finish at all.
    if (timer && typeof timer.unref === "function") timer.unref();
  }

  function tick() {
    timer = null;
    void run();
  }

  async function run() {
    if (stopped) return;
    if (running) {
      // A trigger landed while a read was in flight: one more read after it,
      // never two at once (and never a lost change).
      rerun = true;
      return;
    }
    running = true;
    try {
      await read();
    } catch {
      // `read` paints its own failure words; the poll must survive it.
    } finally {
      running = false;
    }
    if (stopped) return;
    if (rerun) {
      rerun = false;
      return run();
    }
    // The gate's window closing is itself a settled answer: read at the steady
    // rate again, and let the row paint the confirmed value it now holds.
    if (pendingUntil > 0 && !pending()) pendingUntil = 0;
    arm(pending() ? pendingMs : steadyMs);
  }

  /** Ask again on the next turn of the event loop, coalescing triggers. */
  function soon() {
    if (stopped || soonTimer !== null) return;
    soonTimer = setTimeout(() => {
      soonTimer = null;
      void run();
    }, 0);
    if (soonTimer && typeof soonTimer.unref === "function") soonTimer.unref();
  }

  /** A carded save ended before the card was answered: keep re-reading. */
  function hold(ms = pendingCapMs) {
    pendingUntil = now() + Math.max(0, Number(ms) || 0);
    arm(pendingMs);
  }

  /** The card was answered (or the row learned it was never waiting). */
  function release() {
    pendingUntil = 0;
    arm(steadyMs);
  }

  function stop() {
    stopped = true;
    clearTimer();
    if (soonTimer !== null) {
      clearTimeout(soonTimer);
      soonTimer = null;
    }
  }

  if (queue) onQueue(soon);
  if (kinds && kinds.length) {
    onEvent((frame) => {
      if (frame && kinds.includes(frame.kind)) soon();
    });
  }
  if (visible && doc && typeof doc.addEventListener === "function") {
    doc.addEventListener("visibilitychange", soon);
  }
  // The page's first read, through the SAME path as every later one: a boot
  // that read differently from the live path is how the class escaped before.
  soon();

  return { soon, hold, release, pending, stop };
}
