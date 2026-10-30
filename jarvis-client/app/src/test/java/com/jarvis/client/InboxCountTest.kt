package com.jarvis.client

import com.jarvis.client.net.Attention
import com.jarvis.client.ui.screens.budgetLine
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNotEquals
import org.junit.Test

/**
 * The Inbox header's one line: `budgetLine` in `ui/screens/InboxScreen.kt`.
 *
 * The bug this holds shut (B1, phone field test 2026-10-29): the Inbox header
 * read
 *
 *     Inbox / 3 of 3 spoken interruptions left. 0 waiting.
 *
 * printed directly above a card that itself said "Needs your OK / Jarvis wants
 * to switch to a different AI model / Open the card →" - twice, four minutes
 * apart. At that same moment Home said "Connected · 1 waiting", which is the
 * true number: `state.pending.size`, the list the cards come from
 * (`HomeScreen.kt`). The Inbox's "0" was [Attention.pending], the backend's
 * `jarvis_arbiter.pending_count` - queued things Jarvis wants to TELL the
 * owner, which decide nothing about whether a card is waiting - so the header
 * said "nothing is waiting" over something that was.
 *
 * The fix: the line counts the waiting cards ([InboxScreen]'s `pendingCards`,
 * `JarvisRuntime.pending.size`) and makes no waiting claim at all when that is
 * zero. The interruption-budget words are a real fact and stay exactly as they
 * were. These tests are pure JVM - no Compose, no Android - because the sentence
 * is the bug and it is a string.
 */
class InboxCountTest {

    /** The measurement's numbers: a full budget, and an empty arbiter queue. */
    private fun attention(
        remaining: Int = 3,
        limit: Int = 3,
        pending: Int = 0,
        blockedBy: String? = null,
    ) = Attention(remaining = remaining, limit = limit, pending = pending, blockedBy = blockedBy)

    /**
     * THE EVIDENCE, exactly as the phone printed it, with the one waiting card
     * the screen was showing. `pending = 0` is what the backend reported for the
     * arbiter queue; `pendingCards = 1` is what Home's line counted and what the
     * "Needs your OK" card is.
     */
    @Test
    fun `the measured contradiction cannot come back`() {
        val line = budgetLine(attention(pending = 0), pendingCards = 1)
        assertEquals("3 of 3 spoken interruptions left. 1 card waiting.", line)
        assertNotEquals("3 of 3 spoken interruptions left. 0 waiting.", line)
        assertFalse("the header claims nothing is waiting over a waiting card: $line", line.contains("0 waiting"))
    }

    @Test
    fun `two or more waiting cards are counted`() {
        assertEquals(
            "3 of 3 spoken interruptions left. 2 cards waiting.",
            budgetLine(attention(pending = 0), pendingCards = 2),
        )
        assertEquals(
            "3 of 3 spoken interruptions left. 4 cards waiting.",
            budgetLine(attention(pending = 0), pendingCards = 4),
        )
    }

    /**
     * [Attention.pending] is not this line's fact any more. Two queued things to
     * be told put no word "waiting" on the header - that word belongs to the
     * cards, and a count of a different fact under it is what caused the bug.
     */
    @Test
    fun `the arbiter queue is not counted as waiting cards`() {
        val line = budgetLine(attention(pending = 2), pendingCards = 0)
        assertEquals("3 of 3 spoken interruptions left.", line)
        assertFalse("the arbiter queue is back in the header: $line", line.contains("waiting"))
    }

    /**
     * With no card waiting there is no waiting claim at all - not "0 waiting.",
     * which is the sentence that contradicted the card. With no budget reported
     * either, the line is empty and the call site passes null so the top bar
     * draws no second line.
     */
    @Test
    fun `with nothing waiting the line makes no waiting claim`() {
        assertEquals("3 of 3 spoken interruptions left.", budgetLine(attention(), pendingCards = 0))
        assertEquals("", budgetLine(attention(limit = 0), pendingCards = 0))
    }

    /** The budget half is a real fact: exhausted, partly spent, or blocked outright. */
    @Test
    fun `the interruption budget words stay true`() {
        assertEquals(
            "0 of 3 spoken interruptions left.",
            budgetLine(attention(remaining = 0), pendingCards = 0),
        )
        assertEquals(
            "2 of 3 spoken interruptions left.",
            budgetLine(attention(remaining = 2), pendingCards = 0),
        )
        assertEquals("Silent — quiet.", budgetLine(attention(blockedBy = "quiet"), pendingCards = 0))
        assertEquals(
            "Silent — standby. 1 card waiting.",
            budgetLine(attention(blockedBy = "standby"), pendingCards = 1),
        )
        // `blockedBy` still outranks the budget count, as it always did.
        assertEquals(
            "Silent — locked. 2 cards waiting.",
            budgetLine(attention(remaining = 3, blockedBy = "locked"), pendingCards = 2),
        )
    }

    /** A backend that reports no budget but has cards up still says the cards. */
    @Test
    fun `waiting cards are said even with no budget line`() {
        assertEquals("1 card waiting.", budgetLine(attention(limit = 0), pendingCards = 1))
        assertEquals("3 cards waiting.", budgetLine(attention(limit = 0), pendingCards = 3))
    }
}
