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
        // Hidden: Deny is still offered, but it only opens the locked app.
        assertTrue(ApprovalWidgetRules.showsDeny(hidden = true, denyOk = false))
        assertTrue(ApprovalWidgetRules.showsDeny(hidden = false, denyOk = true))
        assertFalse(ApprovalWidgetRules.showsDeny(hidden = false, denyOk = false))
    }

    @Test
    fun `the Mute tile asks for the phone unlock under App lock`() {
        assertTrue(QuickTiles.muteNeedsUnlock(appLock = true, phoneLocked = true))
        assertTrue(QuickTiles.muteNeedsUnlock(appLock = null, phoneLocked = true))
        assertFalse(QuickTiles.muteNeedsUnlock(appLock = true, phoneLocked = false))
        assertFalse(QuickTiles.muteNeedsUnlock(appLock = false, phoneLocked = true))
    }
}
