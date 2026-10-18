package com.jarvis.client

import com.jarvis.client.widget.ApprovalWidgetRules
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

/**
 * Deny is never held while the connection is catching up (2026-10-17).
 *
 * The promise, in the project's own words (the "When the connection is
 * catching up" page): *"Nothing is decided while the stream is stale - refusing
 * is never held, approving can be."* Both apps used to hold BOTH answers, so
 * while the link caught up the owner could not say no.
 *
 * What is testable without a phone is the pure rule the runtime, the card and
 * the widget read ([ApprovalDecisions]) plus the widget's own rule
 * ([ApprovalWidgetRules.denyReachable]); the Compose wiring is compiled by CI
 * and can only be driven on a device, which `ApprovalDecisionTest` says plainly
 * about itself too.
 */
class DenyNotHeldTest {

    @Test
    fun a_stale_stream_holds_approving() {
        assertTrue(
            "approving on a queue that cannot be confirmed must wait",
            ApprovalDecisions.heldOnStale(approve = true, stale = true),
        )
    }

    @Test
    fun a_stale_stream_never_holds_denying() {
        assertFalse(
            "a deny must be sent on a stale link - the owner must be able to say no",
            ApprovalDecisions.heldOnStale(approve = false, stale = true),
        )
    }

    @Test
    fun control_a_live_stream_holds_neither_answer() {
        assertFalse(ApprovalDecisions.heldOnStale(approve = true, stale = false))
        assertFalse(ApprovalDecisions.heldOnStale(approve = false, stale = false))
    }

    /** The words are part of the behaviour: they must not claim the decision
     *  cannot be made, and they must name the direction that still works. */
    @Test
    fun the_stale_words_name_approving_and_say_deny_still_works() {
        val said = LinkWords.DECISION_APPROVE_CATCHING_UP
        assertTrue(said, said.contains("approving waits"))
        assertTrue(said, said.contains("Deny still works here"))
        assertFalse("the old both-directions sentence would be false", said.contains("this decision waits"))
    }

    /** The card shows its Deny button on `denyBlocker == null`. A stale link
     *  must never be the reason that is non-null, so the only blockers left are
     *  the ones that must keep applying to BOTH answers. */
    @Test
    fun a_stale_link_is_not_a_deny_blocker() {
        val staleBlocksDeny = ApprovalDecisions.heldOnStale(approve = false, stale = true)
        assertFalse(staleBlocksDeny)
        // And the widget's own rule agrees: a stale-but-connected link can
        // still carry the deny, a link that is gone cannot carry anything.
        assertTrue(ApprovalWidgetRules.denyReachable(ready = true, connected = true))
        assertFalse(ApprovalWidgetRules.denyReachable(ready = true, connected = false))
        assertFalse(ApprovalWidgetRules.denyReachable(ready = false, connected = true))
    }

    /** App lock is untouched: Deny there still opens the app, never a one-tap
     *  decision. (Unchanged behaviour, pinned so the stale fix cannot drift into
     *  it.) */
    @Test
    fun app_lock_still_routes_deny_through_the_app() {
        assertFalse(ApprovalWidgetRules.denyActsDirectly(hidden = true, denyOk = true))
        assertTrue(ApprovalWidgetRules.denyActsDirectly(hidden = false, denyOk = true))
    }
}
