package com.jarvis.client

/**
 * Which approval answers wait for the event stream to be live again - the one
 * rule the runtime, the card and the widget all read.
 *
 * Pure, so `DenyNotHeldTest` can check the whole matrix without a phone (the
 * runtime it feeds into cannot be constructed off-device).
 *
 * Page 7's promise: *"refusing is never held, approving can be."*
 *
 * APPROVE waits for a queue that can be confirmed live: approving against a
 * picture that may already be answered is how the wrong thing gets approved.
 *
 * DENY never waits, and the 2026-10-17 fix moved it out from under this rule.
 * A stale deny is safe by construction:
 *  - the call is an explicit polarity (`approved = false`), never a toggle, so
 *    it cannot approve anything;
 *  - the card transitions once (`pending -> approved | denied | expired`), so a
 *    deny for a card that is still pending is the answer the owner wanted, and
 *    a late one is refused by the server's own expired / duplicate /
 *    no-longer-pending arm - a refusal, never an approval;
 *  - denying never writes a standing rule (`_NO_RULE_FROM_DENIAL`), so there is
 *    nothing a stale picture can loosen.
 */
object ApprovalDecisions {

    /**
     * Whether this answer has to wait for the event stream to be live.
     *
     * @param approve which answer is being asked about (`true` approve,
     *   `false` deny). The polarity is a parameter because the card greys its
     *   two buttons from two separate calls.
     * @param stale whether the runtime's link is catching up.
     */
    fun heldOnStale(approve: Boolean, stale: Boolean): Boolean = approve && stale
}
