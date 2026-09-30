package com.jarvis.client

import com.jarvis.client.InternalLaunch.Launch
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test
import java.io.File

/**
 * [InternalLaunch.decide]: MainActivity is exported, so START_LIVE, RESUME_LIVE
 * and OPEN_HANDOFF are honoured only with this app's own proof.
 */
class InternalLaunchTest {

    private val secret = "a".repeat(64)

    @Test
    fun `start and resume Live need the proof`() {
        assertEquals(Launch.START_LIVE, InternalLaunch.decide(MainActivity.ACTION_START_LIVE, secret, secret, true))
        assertEquals(Launch.RESUME_LIVE, InternalLaunch.decide(MainActivity.ACTION_RESUME_LIVE, secret, secret, true))
        // Another app: no proof, or a wrong one - only the harmless Live screen opens.
        assertEquals(Launch.OPEN_LIVE_SCREEN, InternalLaunch.decide(MainActivity.ACTION_START_LIVE, null, secret, true))
        assertEquals(Launch.OPEN_LIVE_SCREEN, InternalLaunch.decide(MainActivity.ACTION_START_LIVE, "guess", secret, true))
        assertEquals(Launch.OPEN_LIVE_SCREEN, InternalLaunch.decide(MainActivity.ACTION_RESUME_LIVE, "", secret, true))
    }

    @Test
    fun `a re-created activity never starts Live again`() {
        assertEquals(Launch.OPEN_LIVE_SCREEN, InternalLaunch.decide(MainActivity.ACTION_START_LIVE, secret, secret, false))
        assertEquals(Launch.OPEN_LIVE_SCREEN, InternalLaunch.decide(MainActivity.ACTION_RESUME_LIVE, secret, secret, false))
    }

    @Test
    fun `the handoff screen needs the proof and is otherwise ignored`() {
        assertEquals(Launch.OPEN_HANDOFF, InternalLaunch.decide(MainActivity.ACTION_OPEN_HANDOFF, secret, secret, true))
        assertEquals(Launch.IGNORE, InternalLaunch.decide(MainActivity.ACTION_OPEN_HANDOFF, null, secret, true))
        assertEquals(Launch.IGNORE, InternalLaunch.decide(MainActivity.ACTION_OPEN_HANDOFF, "x", secret, true))
    }

    @Test
    fun `no stored secret means no proof, even an empty one`() {
        assertFalse(InternalLaunch.proves("", ""))
        assertFalse(InternalLaunch.proves(null, null))
        assertFalse(InternalLaunch.proves("x", null))
        assertFalse(InternalLaunch.proves(null, secret))
        assertTrue(InternalLaunch.proves(secret, secret))
        assertEquals(Launch.OPEN_LIVE_SCREEN, InternalLaunch.decide(MainActivity.ACTION_START_LIVE, "", "", true))
    }

    @Test
    fun `opening the Live screen and unrelated actions need nothing`() {
        assertEquals(Launch.OPEN_LIVE_SCREEN, InternalLaunch.decide(MainActivity.ACTION_OPEN_LIVE, null, secret, true))
        assertEquals(Launch.IGNORE, InternalLaunch.decide(MainActivity.ACTION_START_VOICE, secret, secret, true))
        assertEquals(Launch.IGNORE, InternalLaunch.decide(null, secret, secret, true))
    }

    /** Static shortcuts cannot carry a secret, so none may use an action that needs one. */
    @Test
    fun `static shortcuts use none of the proof-only actions`() {
        val xml = repoFile("jarvis-client/app/src/main/res/xml/shortcuts.xml").readText()
        assertFalse(xml.contains("START_LIVE"))
        assertFalse(xml.contains("RESUME_LIVE"))
        assertFalse(xml.contains("OPEN_HANDOFF"))
    }

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
