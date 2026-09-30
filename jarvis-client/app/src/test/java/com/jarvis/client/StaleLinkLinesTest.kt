package com.jarvis.client

import com.jarvis.client.net.BigModel
import com.jarvis.client.net.Hardware
import com.jarvis.client.net.WatchNotify
import com.jarvis.client.net.WebSearch
import com.jarvis.client.net.Wiki
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

/**
 * Settings audit, 2026-09-30: four panels greyed their controls on a stale
 * link (the connection to the PC is behind) without saying why. Each now shows
 * one plain line, in the words every other panel already uses ("Not connected
 * to the desktop, so ... wait until the link is back.").
 */
class StaleLinkLinesTest {

    private val lines = mapOf(
        "Smartwatch notifications" to WatchNotify.STALE,
        "Big model" to BigModel.STALE,
        "Hardware" to Hardware.STALE,
        "Wiki" to Wiki.STALE,
        "Web search" to WebSearch.STALE,
    )

    @Test
    fun `every greyed panel says why, in the shared words`() {
        for ((panel, line) in lines) {
            assertTrue("$panel: starts the shared way", line.startsWith("Not connected to the desktop, so "))
            assertTrue("$panel: says what waits", line.endsWith("until the link is back."))
        }
    }

    @Test
    fun `the watch line shows only when turning it on is what is held`() {
        // Off and the link is stale: turning it ON is held, so say why.
        assertTrue(WatchNotify.showStale(enabled = false, canAct = false, cardWaiting = false))
        // Live link: nothing is held.
        assertFalse(WatchNotify.showStale(enabled = false, canAct = true, cardWaiting = false))
        // Already on: turning it off still works, so nothing to explain.
        assertFalse(WatchNotify.showStale(enabled = true, canAct = false, cardWaiting = false))
        // A card is waiting: its own line already says so.
        assertFalse(WatchNotify.showStale(enabled = false, canAct = false, cardWaiting = true))
        // Unknown: the state line already says it could not tell.
        assertFalse(WatchNotify.showStale(enabled = null, canAct = false, cardWaiting = false))
    }

    @Test
    fun `each line names the thing that is held`() {
        assertTrue(WatchNotify.STALE.contains("turning this on"))
        assertTrue(BigModel.STALE.contains("switches"))
        assertTrue(Hardware.STALE.contains("Measure"))
        assertEquals("Not connected to the desktop, so Add to wiki waits until the link is back.", Wiki.STALE)
    }
}
