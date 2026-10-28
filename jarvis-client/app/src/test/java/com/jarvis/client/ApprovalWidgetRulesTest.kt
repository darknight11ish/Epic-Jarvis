package com.jarvis.client

import com.jarvis.client.data.QuickTiles
import com.jarvis.client.widget.ApprovalWidgetRules
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

/** The approval widget and the Mute tile under App lock (owner, 2026-09-28). */
class ApprovalWidgetRulesTest {

    @Test
    fun `App lock or hidden lists hide the widget, and unreadable settings fail closed`() {
        assertFalse(ApprovalWidgetRules.hidden(true, appLock = false, privateLists = false))
        assertTrue(ApprovalWidgetRules.hidden(true, appLock = true, privateLists = false))
        assertTrue(ApprovalWidgetRules.hidden(true, appLock = false, privateLists = true))
        assertTrue(ApprovalWidgetRules.hidden(false, appLock = false, privateLists = false))
        assertEquals("A decision is waiting", ApprovalWidgetRules.HIDDEN_TITLE)
    }

    @Test
    fun `Deny acts on its own only when nothing is hidden`() {
        assertTrue(ApprovalWidgetRules.denyActsDirectly(hidden = false, denyOk = true))
        assertFalse(ApprovalWidgetRules.denyActsDirectly(hidden = true, denyOk = true))
        assertFalse(ApprovalWidgetRules.denyActsDirectly(hidden = false, denyOk = false))
    }

    /** The owner, 2026-10-28: a button labelled "Deny" that could only open the
     *  app. The label must not promise a decision the tap cannot make, so a
     *  hidden card draws no Deny at all - one button that says what it does. */
    @Test
    fun `a hidden card draws no Deny, only the button that opens the app`() {
        for (denyOk in listOf(false, true)) {
            val buttons = ApprovalWidgetRules.cardButtons(hidden = true, denyOk = denyOk)
            assertEquals("hidden, denyOk=$denyOk: $buttons", 1, buttons.size)
            assertEquals(ApprovalWidgetRules.UNLOCK_LABEL, buttons.single().label)
            assertEquals(ApprovalWidgetRules.Tap.OPEN_APP, buttons.single().tap)
            assertFalse(buttons.any { it.label == "Deny" })
        }
        // Unhidden, the pair is exactly the one every other card draws.
        assertEquals(
            listOf("Deny", "Review"),
            ApprovalWidgetRules.cardButtons(hidden = false, denyOk = true).map { it.label },
        )
        // And an item the PC marked unsafe to refuse unread has no Deny either -
        // the same condition the lock-screen notification already runs on.
        assertEquals(
            listOf("Review"),
            ApprovalWidgetRules.cardButtons(hidden = false, denyOk = false).map { it.label },
        )
    }

    @Test
    fun `the Mute tile asks for the phone unlock under App lock`() {
        assertTrue(QuickTiles.muteNeedsUnlock(appLock = true, phoneLocked = true))
        assertTrue(QuickTiles.muteNeedsUnlock(appLock = null, phoneLocked = true))
        assertFalse(QuickTiles.muteNeedsUnlock(appLock = true, phoneLocked = false))
        assertFalse(QuickTiles.muteNeedsUnlock(appLock = false, phoneLocked = true))
    }
}
