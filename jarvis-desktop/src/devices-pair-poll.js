/**
 * devices-pair-poll.js - how often the pairing panel re-reads the session
 * (2026-10-08 cohesion audit, finding 1).
 *
 * The panel used to run `POLL_MS = 2000` in a flat `setInterval` for the whole
 * life of a pairing. Measured over one simulated minute with a code on screen
 * (`tests/timers.mjs`): 30 `pair_session` reads, against the 15-20 s cadence
 * the rest of the app's own panels poll at (`src/brain.js`).
 *
 * WHAT THE FAST READ IS FOR, and why it is not simply deleted: the four words
 * the owner compares against the card arrive with the phone's claim, and the
 * backend does not publish a `devices` event for that claim - `_publish` in
 * `backend/jarvis_devices.py` fires on a registry change (paired at :1645,
 * removed at :1754, shared at :1794/:1831, a signing key at :2086/:2105) and
 * `claim()` (:1529) is none of those, it only `_audit`s. So without a read of
 * `pair_session` there is no path at all from "the phone asked" to those words
 * on screen. THE DEVICE LIST is a different matter and is not polled: it is
 * re-read by the `devices` event handler, which is the freshness the audit
 * asked for.
 *
 * SO THE WAIT FOLLOWS THE SESSION. The two seconds only have to cover the
 * moment the owner holds the phone up to the code; after that the panel is
 * waiting on a person. One minute of two-second reads, then the app's own slow
 * cadence. Over a full ten-minute code that is about 66 reads against 300 -
 * and the QR moment is untouched.
 */

/** While the phone is likely to be pointed at the code: the old 2 s. */
export const POLL_MS_HOT = 2000;

/** After that: the 15 s `brain.js` uses for its own panels. */
export const POLL_MS_COOL = 15000;

/** How long the fast stretch lasts: long enough to scan a QR code. */
export const HOT_WINDOW_MS = 60000;

/**
 * How long to wait before the next `pair_session` read.
 *
 * @param {number} shownAt   when the code went on screen (ms, `Date.now()`)
 * @param {number} now       the time asking (ms)
 * @returns {number} ms to wait; the fast wait inside the window, the slow one
 *                   after it, and the fast one again when `shownAt` is not a
 *                   time at all (a panel whose clock has not started yet must
 *                   not wait fifteen seconds for its first words).
 */
export function pairWaitMs(shownAt, now) {
  if (!Number.isFinite(shownAt) || !Number.isFinite(now) || shownAt <= 0) return POLL_MS_HOT;
  return now - shownAt < HOT_WINDOW_MS ? POLL_MS_HOT : POLL_MS_COOL;
}
