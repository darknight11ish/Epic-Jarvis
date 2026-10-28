package com.jarvis.client

import com.jarvis.client.data.QuickTiles
import com.jarvis.client.widget.ApprovalWidgetRules
import com.jarvis.client.widget.ApprovalWidgetRules.WidgetButton
import com.jarvis.client.widget.ApprovalWidgetRules.WidgetButtonPlan
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

/** The approval widget and the Mute tile under App lock (owner, 2026-09-28),
 *  and Deny's own rule (owner, 2026-10-28). */
class ApprovalWidgetRulesTest {

    private val bools = listOf(false, true)

    @Test
    fun `App lock or hidden lists hide the widget, and unreadable settings fail closed`() {
        assertFalse(ApprovalWidgetRules.hidden(true, appLock = false, privateLists = false))
        assertTrue(ApprovalWidgetRules.hidden(true, appLock = true, privateLists = false))
        assertTrue(ApprovalWidgetRules.hidden(true, appLock = false, privateLists = true))
        assertTrue(ApprovalWidgetRules.hidden(false, appLock = false, privateLists = false))
        assertEquals("A decision is waiting", ApprovalWidgetRules.HIDDEN_TITLE)
    }

    /**
     * The owner's bug, pinned (2026-10-28). On v0.2.2979, with the phone in
     * App lock / private view, the widget showed Deny and Review, the owner
     * tapped Deny, and it only opened the app. A refusal is the safe
     * direction: the CARD's permission decides, not the lock.
     */
    @Test
    fun `Deny acts on its own whenever the card allows an unread deny`() {
        assertTrue(ApprovalWidgetRules.denyActsDirectly(denyOk = true))
        assertFalse(ApprovalWidgetRules.denyActsDirectly(denyOk = false))
    }

    /**
     * All four hidden x denyOk combinations: what the card draws, and whether
     * any of it is a "Deny" that would only open the app.
     */
    @Test
    fun `the four App-lock and denyOk combinations decide the buttons`() {
        val denyAndReview = listOf(
            WidgetButtonPlan(WidgetButton.DENY, label = "Deny"),
            WidgetButtonPlan(WidgetButton.REVIEW, label = "Review"),
        )
        for (hidden in bools) {
            // The card allows an unread deny. Deny is drawn, and it really
            // denies - with the lock on exactly as with it off.
            assertEquals(
                "hidden=$hidden: a card that allows an unread deny keeps Deny",
                denyAndReview,
                ApprovalWidgetRules.buttons(hidden = hidden, denyOk = true),
            )
            // The card says the denial needs the app. ONE action, it opens the
            // app, and nothing on the card says "Deny" - a button must not
            // promise a refusal it will not perform.
            val noDeny = ApprovalWidgetRules.buttons(hidden = hidden, denyOk = false)
            assertEquals("hidden=$hidden: one truthful action", 1, noDeny.size)
            assertEquals("hidden=$hidden", WidgetButton.REVIEW, noDeny.single().button)
            assertFalse("hidden=$hidden: never a bare Deny", noDeny.single().label == "Deny")
        }
        // The word differs on purpose: unhidden the card names where Deny went;
        // hidden it keeps to the one public word it has always used.
        assertEquals("Deny in app", ApprovalWidgetRules.buttons(hidden = false, denyOk = false).single().label)
        assertEquals("Review", ApprovalWidgetRules.buttons(hidden = true, denyOk = false).single().label)
    }

    @Test
    fun `the Mute tile asks for the phone unlock under App lock`() {
        assertTrue(QuickTiles.muteNeedsUnlock(appLock = true, phoneLocked = true))
        assertTrue(QuickTiles.muteNeedsUnlock(appLock = null, phoneLocked = true))
        assertFalse(QuickTiles.muteNeedsUnlock(appLock = true, phoneLocked = false))
        assertFalse(QuickTiles.muteNeedsUnlock(appLock = false, phoneLocked = true))
    }
}
