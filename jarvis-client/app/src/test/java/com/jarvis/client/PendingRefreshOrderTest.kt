package com.jarvis.client

import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

/**
 * Ordering of overlapping approval-queue reads (the 2026-10-30 follow-up to
 * the owner's card-sync report).
 *
 * The runtime cannot be built in a JVM test (it is a singleton that takes a
 * `Context` and starts collectors), so the ordering rule lives in
 * [PendingRefreshOrder], which is pure. These tests drive the same sequence the
 * runtime does: a slow read that started BEFORE a decision completes, and the
 * decision's own read that starts after it.
 */
class PendingRefreshOrderTest {

    /**
     * THE race: the 30-second beat's GET is issued while a card waits, the
     * owner denies the card, the decision's own refresh lands with an empty
     * queue - and then the beat's older answer arrives with the pre-decision
     * list. Applied, that puts the resolved card (and its drawer notification)
     * back for up to another 30 seconds, which is the exact defect the beat
     * exists to remove.
     */
    @Test
    fun `a slow pre-decision response cannot overwrite the post-decision empty list`() {
        val order = PendingRefreshOrder()
        // The card is on screen when the beat sends its GET.
        var queue = listOf("a1")
        val beat = order.begin()

        // The owner denies it. The decision's read starts after the beat's and
        // is therefore the newest; it lands with an empty queue.
        val decision = order.begin()
        assertTrue(
            "the decision's own refresh is the newer read and must apply",
            order.applyIfLatest(decision) { queue = emptyList() },
        )
        assertEquals(emptyList<String>(), queue)

        // The beat's older answer now arrives.
        val applied = order.applyIfLatest(beat) { queue = listOf("a1") }
        assertFalse("the beat's pre-decision answer must be dropped", applied)
        assertEquals(
            "an answered card must not be re-added by a slow beat response",
            emptyList<String>(),
            queue,
        )
    }

    /** Numbers only ever go up, so "newer" is well defined. */
    @Test
    fun `generation numbers only ever increase`() {
        val order = PendingRefreshOrder()
        val first = order.begin()
        val second = order.begin()
        val third = order.begin()
        assertTrue(
            "begin must hand out a newer number every time: $first, $second, $third",
            first < second && second < third,
        )
    }

    /**
     * A superseded FAILURE must be dropped too. A beat's older GET timing out
     * after the decision's refresh succeeded would otherwise set `stale` and a
     * notice on a queue that was just confirmed live - the phone version of
     * "a failed read blocks Approve".
     */
    @Test
    fun `a superseded failure cannot mark a fresh success stale`() {
        val order = PendingRefreshOrder()
        var queue = listOf("a1")
        var stale = true

        val slowBeat = order.begin()
        val decision = order.begin()
        order.applyIfLatest(decision) {
            queue = emptyList()
            stale = false
        }
        assertFalse("the decision's success opens the gate", stale)

        val applied = order.applyIfLatest(slowBeat) { stale = true }
        assertFalse("a superseded failure must be dropped", applied)
        assertFalse("the fresh success must stay fresh", stale)
        assertEquals(emptyList<String>(), queue)
    }

    /**
     * And the documented safe direction for the other order: when the NEWEST
     * read failed, the old queue stays exactly as it was and the gate stays
     * shut. An older success must not sneak past it either, because a queue
     * read before a decision cannot be trusted after it.
     */
    @Test
    fun `a newer failure leaves the old queue in place and the gate shut`() {
        val order = PendingRefreshOrder()
        var queue = listOf("a1")
        var stale = false

        val beat = order.begin()
        val decision = order.begin()
        // The newest read fails: its handler closes the gate and leaves the
        // queue untouched.
        assertTrue("the newest failure is applied", order.applyIfLatest(decision) { stale = true })
        assertFalse(
            "the older success must not overwrite after a newer failure",
            order.applyIfLatest(beat) { queue = emptyList() },
        )
        assertEquals("the old queue stays as it was", listOf("a1"), queue)
        assertTrue("and the gate stays shut", stale)
    }
}
