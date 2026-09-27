/**
 * heavy-approve.js - "Slower Approve on risky cards" (feasibility I110).
 *
 * `notice.weight: "heavy"` already exists (docs/ARCHITECTURE.md §3): earned
 * by an action that cannot be undone, leaves this machine, or had its tier
 * pushed up by outside text. This module is the one place both desktop
 * surfaces (the Jarvis bar, `main.js`; the widget, `widget.js`) keep such a
 * card's Approve button disabled for a moment, so it cannot be rubber-
 * stamped the instant it appears.
 *
 * TWO CONDITIONS, BOTH MUST CLEAR:
 *   1. `MIN_DELAY_MS` has passed since the card appeared.
 *   2. The card's text has been "in view": either it never needed to
 *      scroll (its whole height already fits its scroll container), or the
 *      owner has scrolled that container to its own bottom at least once.
 * Deny is never touched - refusing something unread costs a retry;
 * approving it is the thing this whole feature exists to slow down.
 * NOTIFICATION cards never had an Approve button at all
 * (`notice.approve_ok` is always `false`, docs/ARCHITECTURE.md §3) and
 * nothing here changes that.
 *
 * STRICTER ONLY: a `"normal"`-weight card, or a card with no `notice` at
 * all (an older backend, or a row this normaliser could not read), is
 * untouched - [`isHeavy`] returns `false` for both, so callers keep doing
 * exactly what they did before this feature existed.
 */

/** How long Approve stays disabled at minimum, whatever else is true. */
export const MIN_DELAY_MS = 2000;

/** Is this a card `notice.weight` calls heavy? Missing `notice` (an older
 * backend, or a row this app's normaliser could not build one for) is
 * treated as `"normal"` - see the module doc comment's "stricter only". */
export function isHeavy(approval) {
  return Boolean(approval && approval.notice && approval.notice.weight === "heavy");
}

/**
 * Tracks the two gates for ONE card at a time. `scrollEl` is measured
 * lazily (its content is usually replaced in the same tick this is
 * started, before layout has run), so [`HeavyGate.check`] is also called
 * from a `requestAnimationFrame` once by [`HeavyGate.start`] and should be
 * called again by the caller after anything that can change the content's
 * height (a note field expanding the card, for instance).
 */
export class HeavyGate {
  /** @param {{scrollEl?: Element, onChange?: () => void, delayMs?: number}} opts */
  constructor({ scrollEl = null, onChange = null, delayMs = MIN_DELAY_MS } = {}) {
    this.scrollEl = scrollEl;
    this.onChange = onChange;
    this.delayMs = delayMs;
    this.timeOk = false;
    this.scrollOk = false;
    this._timer = null;
    this._onScroll = () => this.check();
  }

  /** True once BOTH conditions have cleared for the card currently tracked. */
  get ok() {
    return this.timeOk && this.scrollOk;
  }

  /** Re-measures the scroll condition and fires `onChange` if anything
   * about `ok` could have moved. Safe to call as often as wanted - it is
   * idempotent once both conditions are already satisfied. */
  check() {
    const was = this.ok;
    if (!this.scrollEl) {
      this.scrollOk = true;
    } else {
      const fits = this.scrollEl.scrollHeight <= this.scrollEl.clientHeight + 1;
      const atBottom =
        this.scrollEl.scrollTop + this.scrollEl.clientHeight >= this.scrollEl.scrollHeight - 1;
      this.scrollOk = this.scrollOk || fits || atBottom;
    }
    if (this.ok !== was && this.onChange) this.onChange();
  }

  /** Begins tracking a freshly-opened card. Call this ONLY when the card is
   * actually a new one (a different id) - restarting the clock on every
   * re-render of the SAME card would let a backend that resyncs the queue
   * every few seconds hold Approve disabled forever. */
  start() {
    this.stop();
    this.timeOk = false;
    this.scrollOk = false;
    this._startedAt = Date.now();
    this._timer = setTimeout(() => {
      this._timer = null;
      const was = this.ok;
      this.timeOk = true;
      if (this.ok !== was && this.onChange) this.onChange();
    }, this.delayMs);
    if (this.scrollEl) this.scrollEl.addEventListener("scroll", this._onScroll);
    // The content this gate watches is usually replaced in the same tick
    // this runs, before the browser has laid it out - `scrollHeight` would
    // read as 0 measured synchronously here.
    if (typeof requestAnimationFrame === "function") {
      requestAnimationFrame(() => this.check());
    } else {
      this.check();
    }
  }

  /** Stops watching (a card closed, or a different one is about to start).
   * Deliberately does NOT reset `timeOk`/`scrollOk` - only `start()` does,
   * because a caller that wants "where is this card's gate right now"
   * without restarting the clock (this module's own tests) calls this. */
  stop() {
    if (this._timer !== null) {
      clearTimeout(this._timer);
      this._timer = null;
    }
    if (this.scrollEl) this.scrollEl.removeEventListener("scroll", this._onScroll);
  }

  /** How long is left of the fixed delay, in whole seconds rounded up - for
   * a countdown line ("Read the whole card, or wait 1s…"). 0 once it has
   * elapsed. Approximate on purpose: this is words on screen, not a timer
   * anything is synchronised to. */
  secondsLeft(now = Date.now()) {
    if (this.timeOk) return 0;
    if (this._startedAt === undefined) return Math.ceil(this.delayMs / 1000);
    return Math.max(0, Math.ceil((this._startedAt + this.delayMs - now) / 1000));
  }
}
