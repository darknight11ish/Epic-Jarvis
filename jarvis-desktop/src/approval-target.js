/**
 * Which card a decision belongs to — the widget's wrong-card fix
 * (docs/DEEP-AUDITS-2026-10-05.md §5, finding 1).
 *
 * The widget has ONE pair of Approve and Deny buttons, and one card whose words
 * are replaced whenever the queue changes (widget.js, `onQueue` ->
 * `openApproval`). A card decided somewhere else — the phone, the Jarvis bar,
 * another window — leaves the queue, the next one slides into slot 0, and the
 * two buttons stay exactly where they were. A click aimed at the card the owner
 * was reading then decided a card they had never seen: the widget's `decide()`
 * read `state.approval`, which by then was the new card, and the queue lookup
 * that could have caught it was never made. `syncApprovalButtons` cannot catch
 * it either — it disables the buttons for a stale or in-flight decision, which
 * is a different thing from a swapped card.
 *
 * So the id is captured when the buttons are PRESSED, not when the click lands,
 * and it is looked up in the queue that is live at that moment. That is the
 * same shape as `main.js`'s `openDigestApproval`, which looks a digest row's id
 * up in `currentQueue()` before it opens a card and says "that one has already
 * been answered" when it is gone — reusing it here rather than inventing a
 * second rule.
 *
 * A pressed card that has left the queue is NOT decided, and NOT swapped for
 * whoever replaced it: [`ApprovalTarget.resolve`] returns no card, and the
 * widget says so in one visible sentence. Deny is refused the same way as
 * Approve for the same reason — "deny whatever is on screen now" is the same
 * wrong-card decision with the opposite sign.
 *
 * Nothing here decides anything. It names the card; the caller still goes
 * through `decide_approval` in Rust, which is the one place a decision is sent.
 */

/** The widget's one-line status when the pressed card went away. */
export const GONE_LINE = "That card was answered elsewhere, so nothing was sent.";
/** The same, as the flash line's title: 320px cuts the short version off. */
export const GONE_DETAIL =
  "The card you pressed was answered somewhere else first — on the phone, or in the Jarvis bar — "
  + "so nothing was sent from here. The card on screen now is a different one: read it before deciding.";

export class ApprovalTarget {
  constructor() {
    /** The card this window last put on screen (`openApproval`). */
    this.painted = null;
    /** The card the owner's finger, Enter or Space came down on, or null. */
    this.pressed = null;
  }

  /** A card was painted. Called by `openApproval`, which is the paint. */
  paint(id) {
    this.painted = id === null || id === undefined ? null : String(id);
  }

  /** The card left this window: nothing left to press, and nothing to decide. */
  clear() {
    this.painted = null;
    this.pressed = null;
  }

  /**
   * The buttons were pressed. Remembers WHICH card that press belonged to,
   * before anything can repaint under it — which is the whole point: by the
   * time the click arrives, `paint()` may already have been called with a
   * different card. Returns the pinned id, or null when there was no card.
   */
  press() {
    this.pressed = this.painted;
    return this.pressed;
  }

  /** The press never became a click (a cancelled or dragged-away pointer).
   *  Without this, the pin would survive and be spent by the NEXT decision. */
  forgetPress() {
    this.pressed = null;
  }

  /**
   * The card a decision belongs to, and whether one may be sent at all:
   * `{ id, card, gone }`.
   *
   * The pressed card wins over the painted one — it is the card that was on
   * screen when the decision was aimed. Either way the id must still be in the
   * live queue: a card that has left it was answered, expired or withdrawn, and
   * a decision for it would be a decision about a card nobody is looking at.
   * `card` is the queue's OWN row, not a remembered copy, so the caller reads
   * `risk` and `notice` from the same place every other surface does.
   */
  resolve(queue) {
    const id = this.pressed || this.painted;
    if (!id) return { id: null, card: null, gone: false };
    const items = queue && Array.isArray(queue.items) ? queue.items : [];
    const card = items.find((item) => item && String(item.id) === String(id)) || null;
    return { id, card, gone: !card };
  }
}
