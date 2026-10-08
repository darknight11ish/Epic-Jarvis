/**
 * clock-timer.js - the self-aligning ticker behind the approval clock
 * (2026-10-08 cohesion audit, finding 2).
 *
 * The Jarvis bar (`main.js`) and the widget (`widget.js`) each used to own a
 * bare `setInterval(..., 1000)` whose only job was to repaint the one line
 * under the risk row. Measured over one simulated minute (`tests/timers.mjs`,
 * 2026-10-08), that callback ran 60 times even with NO card on screen and
 * nothing to say - and it ran whether or not anybody was looking at the
 * window.
 *
 * TWO THINGS WERE WRONG, and this module fixes each:
 *
 * 1. A flat one-second interval wakes whether or not the shown words can have
 *    changed. So the wait is computed per wake instead: ask `delay` how long
 *    the line is worth, then sleep exactly that. Idle (no card, or no clock
 *    on it) the answer is a minute; while the card's own "3:59 left to decide"
 *    and the heavy-approve "Approve unlocks in 2s" are counting down, the
 *    answer is only the remainder of the second being shown - a self-aligning
 *    tick, so the digits change on the second and never later.
 *
 *    A minute boundary is NOT the right wait for this clock, however tempting
 *    it looks from the audit's summary. `expiryWords` (jarvis-link.js) prints
 *    "M:SS left to decide", and `HeavyGate.secondsLeft` (heavy-approve.js)
 *    prints whole seconds; both change every second they are on screen. This
 *    is written down here because the audit's "something that changes 60
 *    times an hour" is true of an hour-and-minute clock and not of this one.
 *
 * 2. A hidden window kept ticking. Every other reader in this app already
 *    treats a hidden window as "no reason to work" (`visibilitychange` in
 *    `hardware-panel.js`, `settings.js`, `brain.js` - the big, repeated
 *    pattern), so this one stops while the document is hidden and re-arms
 *    with one fetch on the way back. The same `hidden` reading also parks the
 *    timer in the "wait a minute" branch while the page is not visible.
 *
 * NOT a wall clock: `setTimeout` rather than `setInterval`, so a slow paint
 * cannot stack up a backlog of ticks, and a surface that goes idle between
 * two wakes stops paying for the second-level cadence the moment it does.
 */

/**
 * Milliseconds left until the second being shown turns over - a self-aligning
 * wait measured on the real clock, so waking late never skips a digit.
 * Injected in tests so the wake-up count can be measured without waiting.
 */
export const alignMs = (now = Date.now()) => 1000 - (now % 1000);

/** The wait an idle surface sleeps: the app's own slow cadence (`brain.js`). */
export const IDLE_MS = 60000;

/**
 * A repeating paint that pays only for the seconds it can actually show.
 *
 * @param {() => void} paint       repaints the line; called once now, then on every wake
 * @param {object} opts
 * @param {() => number} opts.delay  how long until the shown words can change, in ms
 *                                    (the minimum wait; the align step is added on top)
 * @param {() => boolean} [opts.hidden]  whether this window is out of sight (default: document)
 * @param {string} [opts.name]  a name for the test-only wake-up counter
 * @param {(fn: () => void, ms: number) => unknown} [opts.schedule]  the timer to arm
 * @param {(id: unknown) => void} [opts.cancel]  to drop an armed one
 * @param {() => number} [opts.now]  the clock the alignment is measured on
 * @param {(fn: () => void) => () => void} [opts.visibility]  "call me when this
 *        window is shown or hidden again", returning its own unsubscribe
 * @returns {{wake: () => void, stop: () => void}}
 *
 * The last four are for tests only, and are the pattern `inbox-tidy.js`
 * already uses (`setTimer` / `visible`): the unit half of `tests/timers.mjs`
 * drives the tick by hand rather than stubbing `setTimeout` on the global,
 * which in Node reaches into every other module in the process.
 */
export function clockTimer(paint, { delay, hidden, name = "", schedule, cancel, now,
                                    visibility } = {}) {
  if (typeof delay !== "function") throw new TypeError("clockTimer needs delay()");
  const isHidden = hidden || (() => typeof document !== "undefined" && Boolean(document.hidden));
  const set = schedule || ((fn, ms) => setTimeout(fn, ms));
  const clear = cancel || ((id) => clearTimeout(id));
  const clockNow = now || (() => Date.now());
  const onVisibility = visibility || ((fn) => {
    if (typeof document === "undefined" || !document.addEventListener) return () => {};
    document.addEventListener("visibilitychange", fn);
    return () => document.removeEventListener("visibilitychange", fn);
  });
  let timer = null;
  let unwatch = null;
  let stopped = false;
  let lastWait = IDLE_MS;

  const counts = (globalThis.__jarvisClockWakes ||= {});
  const count = () => { counts[name] = (counts[name] || 0) + 1; };

  const arm = () => {
    lastWait = isHidden() ? IDLE_MS : Math.max(delay(), 0) + alignMs(clockNow());
    timer = set(wake, lastWait);
  };

  function wake() {
    timer = null;
    count();
    if (isHidden()) return arm();      // out of sight: hold the slow beat, paint nothing
    // A wake is only worth a repaint if the wait that just ran was a
    // second-level one. An idle wake (the line had nothing to show when it was
    // armed) re-reads the wait and stops there, which is what the old flat
    // interval did 60 times a minute for nothing.
    const wasShowing = lastWait < IDLE_MS;
    arm();
    if (wasShowing) paint();
  }

  const onShown = () => {
    if (stopped) return;
    if (isHidden()) {
      // Nothing to show, and nothing to keep watch for until it is seen again:
      // drop the pending wake and let the next visibility change restart it.
      if (timer !== null) { clear(timer); timer = null; }
      lastWait = IDLE_MS;
      return;
    }
    // Back on screen: repaint at once - the countdown moved while it was away -
    // and resume the second-level beat.
    if (timer === null) { paint(); arm(); }
  };

  unwatch = onVisibility(onShown);

  const api = {
    /**
     * Paints now and arms the next wake - for a wake that has a reason.
     *
     * Called when what this timer watches changes (a card opened, closed or
     * replaced). Without it a clock that was idle when the change happened
     * would sit on a minute-long wait and show a frozen countdown: the
     * failure this whole module exists to prevent, in the other direction.
     */
    wake() {
      if (stopped) return;
      if (timer !== null) { clear(timer); timer = null; }
      if (isHidden()) return arm();
      paint();
      arm();
    },
    stop() {
      stopped = true;
      if (timer !== null) { clear(timer); timer = null; }
      if (unwatch) { unwatch(); unwatch = null; }
    },
  };
  return api;
}