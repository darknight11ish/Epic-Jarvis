package com.jarvis.client

import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test
import java.io.File

/**
 * [LinkWords]: a link that is catching up and a link that is gone get
 * different words, and neither lets a decision through (rule 4) - phone
 * walk-through, 2026-09-27.
 */
class LinkWordsTest {

    @Test
    fun `every state that is not connected-and-trusted still blocks a decision`() {
        // The gate every caller used before: stale OR not connected.
        for (link in LinkState.values()) {
            for (stale in listOf(true, false)) {
                val blocked = LinkWords.decisionBlocked(link, stale)
                val shouldBlock = stale || link != LinkState.CONNECTED
                assertEquals("$link stale=$stale", shouldBlock, blocked != null)
            }
        }
    }

    @Test
    fun `a link that is up but catching up does not say not connected`() {
        assertEquals(
            LinkWords.DECISION_CATCHING_UP,
            LinkWords.decisionBlocked(LinkState.CONNECTED, stale = true),
        )
        assertFalse(LinkWords.DECISION_CATCHING_UP.contains("Not connected"))
        assertTrue(LinkWords.DECISION_CATCHING_UP.contains("waits"))
    }

    @Test
    fun `a link that is really down still says not connected`() {
        for (link in listOf(LinkState.OFFLINE, LinkState.RECONNECTING)) {
            assertEquals(LinkWords.DECISION_NOT_CONNECTED, LinkWords.decisionBlocked(link, stale = true))
        }
        assertNull(LinkWords.decisionBlocked(LinkState.CONNECTED, stale = false))
    }

    @Test
    fun `coming back to the app reconnects only a link that is catching up for a reason`() {
        // The case this is for: the watchdog heard nothing for a while.
        assertTrue(LinkWords.reconnectOnReturn(LinkState.CONNECTED, true, "No keepalive for 75s"))
        assertTrue(LinkWords.reconnectOnReturn(LinkState.CONNECTED, true, "Could not re-read what is waiting"))
        // A connection that has just opened and is reading for the first
        // time: connected, not yet trusted, no reason - left alone.
        assertFalse(LinkWords.reconnectOnReturn(LinkState.CONNECTED, true, null))
        // A live, trusted link.
        assertFalse(LinkWords.reconnectOnReturn(LinkState.CONNECTED, false, null))
        // An attempt already under way, or an offline link retrying on its
        // own (Home has Retry for that one).
        assertFalse(LinkWords.reconnectOnReturn(LinkState.RECONNECTING, true, "No keepalive for 75s"))
        assertFalse(LinkWords.reconnectOnReturn(LinkState.OFFLINE, true, "connection refused"))
    }

    /**
     * One word for the state on both of the phone's screens that name it,
     * the same word the desktop's jarvis-link.js uses (tests/continuity.mjs
     * holds Home and the desktop to it). The Connection card on Checks used
     * to say "Stale".
     */
    @Test
    fun `Home and Checks call it the same thing`() {
        val screens = "jarvis-client/app/src/main/java/com/jarvis/client/ui/screens/"
        val home = repoFile(screens + "HomeScreen.kt").readText()
        val checks = repoFile(screens + "ReadinessScreen.kt").readText()
        val word = "\"${LinkWords.CATCHING_UP}\""
        assertTrue("HomeScreen.kt does not say $word", home.contains(word))
        assertTrue("ReadinessScreen.kt does not say $word", checks.contains(word))
        assertFalse("ReadinessScreen.kt still says \"Stale\"", checks.contains("\"Stale\""))
    }

    /** Walks up from Gradle's working folder (`jarvis-client/app`) to the repository. */
    private fun repoFile(rel: String): File {
        var dir: File? = File(System.getProperty("user.dir") ?: ".").absoluteFile
        while (dir != null) {
            val f = File(dir, rel)
            if (f.isFile) return f
            dir = dir.parentFile
        }
        error("$rel not found above ${System.getProperty("user.dir")}")
    }
}
