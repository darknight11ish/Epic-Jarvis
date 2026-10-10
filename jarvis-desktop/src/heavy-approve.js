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
 *
 * ALSO HERE: [`needsFullCard`] - the same thought taken one step further.
 * A card whose reach or reversibility matters may not be decided on a surface
 * that clamps its text to two lines, whether or not the backend labelled it
 * `heavy`. The widget redirects those to the Jarvis bar, exactly as it
 * already does for App lock and email cards. See that function's own comment.
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
 * Does deciding this card need the WHOLE card, not the widget's two clamped
 * lines? (docs/DEEP-AUDITS-2026-10-05.md finding D1; docs/HANDOFF-UI-RESEARCH-
 * 2026-10-09.md Phase A(b); docs/SUMMARY-UI-RESEARCH-2026-10-09.md "a second,
 * smaller bug in the same widget".)
 *
 * `isHeavy` alone was not enough. It reads `notice.weight`, so a card the
 * backend did not label - an older backend, or a row whose `notice` this
 * app's normaliser could not build - read as `"normal"`, and a 320x44 strip
 * with two clamped lines could approve something that sends email or switches
 * the model. The widget's own `.appr-detail` is `-webkit-line-clamp: 2` on
 * purpose (widget.css), so "the whole text has been in view" is a claim that
 * surface cannot honestly make about ANY card whose reach or reversibility
 * matters - labelled or not.
 *
 * So this reads the data every card already carries and never invents a
 * default in the unsafe direction:
 *
 *   - `risk` missing or unreadable (`null`, `{}`) -> `true`. A backend that
 *     sends no risk classification has not told this surface what the action
 *     costs, and the app must not guess "cheap". `riskLine()` in
 *     `jarvis-link.js` already treats the same input as
 *     "not classified, so treat it as irreversible" - this is that sentence,
 *     as a gate.
 *   - `risk.reach !== "local"` -> `true`. It leaves this PC.
 *   - `risk.reversible !== "yes"` -> `true`. It cannot simply be undone
 *     ("hard" and "no" alike; the card's own line says which).
 *
 * `false` therefore means exactly one thing: a card that stays on this
 * machine, can be undone, and said so. That is the only shape the widget's
 * clamped strip may decide by itself.
 *
 * NOTE the deliberate asymmetry with [`isHeavy`], which stays `"stricter
 * only"`: this is a *redirect*, not a lock-out. A `true` here only sends the
 * decision to the Jarvis bar, where the whole card is shown and Windows Hello
 * decides - it never disables Deny, and it never decides anything by itself.
 */
export function needsFullCard(approval) {
  if (!approval) return true;
  const risk = approval.risk;
  if (!risk || typeof risk !== "object") return true;
  return risk.reach !== "local" || risk.reversible !== "yes";
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
