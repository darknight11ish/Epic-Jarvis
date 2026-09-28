package com.jarvis.client

import com.jarvis.client.net.Sayable
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test
import java.io.File

/**
 * [AppShortcuts]: the "Brief me now" and "What did I miss?" app-icon
 * shortcuts ask their sentence on Home (phone walk-through, 2026-09-27).
 */
class AppShortcutsTest {

    @Test
    fun `each shortcut asks its own sentence and nothing else does`() {
        assertEquals("Brief me now.", AppShortcuts.questionFor(AppShortcuts.ACTION_ASK_BRIEF))
        assertEquals("What did I miss?", AppShortcuts.questionFor(AppShortcuts.ACTION_ASK_MISSED))
        // Every other action MainActivity reads - and none at all - asks nothing.
        assertNull(AppShortcuts.questionFor(null))
        assertNull(AppShortcuts.questionFor("com.jarvis.client.action.OPEN_BRIEFING"))
        assertNull(AppShortcuts.questionFor("com.jarvis.client.action.START_VOICE"))
        assertNull(AppShortcuts.questionFor("android.intent.action.MAIN"))
    }

    /**
     * Only sentences from "Things you can say" - the list the backend's own
     * test_sayable.py proves are answered without the AI model. A shortcut
     * must never send anything that could reach the model or change a thing.
     */
    @Test
    fun `both sentences are on the Things you can say list`() {
        assertTrue(AppShortcuts.BRIEF_ME in Sayable.SENTENCES)
        assertTrue(AppShortcuts.WHAT_DID_I_MISS in Sayable.SENTENCES)
    }

    @Test
    fun `shortcuts xml fires the two actions and no longer just opens Brain`() {
        val xml = repoFile("jarvis-client/app/src/main/res/xml/shortcuts.xml").readText()
        assertTrue(xml.contains("android:action=\"${AppShortcuts.ACTION_ASK_BRIEF}\""))
        assertTrue(xml.contains("android:action=\"${AppShortcuts.ACTION_ASK_MISSED}\""))
        assertFalse(xml.contains("android:action=\"com.jarvis.client.action.OPEN_BRIEFING\""))
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
