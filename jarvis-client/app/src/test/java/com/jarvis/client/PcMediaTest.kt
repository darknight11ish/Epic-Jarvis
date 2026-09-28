package com.jarvis.client

import com.jarvis.client.net.ApiError
import com.jarvis.client.net.JarvisJson
import com.jarvis.client.net.PcMedia
import kotlinx.serialization.json.JsonObject
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test
import java.io.File

/**
 * "Playing on your PC" on Home (net/PcMedia.kt; backend jarvis_media.py):
 * four buttons, ONE action each, only the PC's own four, and the PC's own
 * sentence shown back.
 */
class PcMediaTest {
    private fun obj(s: String) = JarvisJson.parseToJsonElement(s) as JsonObject

    @Test
    fun onlyThePcsFourActionsOneAtATime() {
        assertEquals(listOf("previous", "play", "pause", "next"), PcMedia.ACTIONS)
        assertEquals("{\"action\":\"pause\"}", PcMedia.body("pause"))
        assertNull(PcMedia.body("volume_up"))
        assertNull(PcMedia.body("all"))
        assertEquals(listOf("Previous", "Play", "Pause", "Next"), PcMedia.ACTIONS.map(PcMedia::label))
    }

    @Test
    fun thePcsOwnSentenceIsShown() {
        assertEquals("Paused.", PcMedia.said(obj("""{"ok":true,"said":"Paused."}""")))
        assertEquals(
            "Nothing seems to be playing right now.",
            PcMedia.said(obj("""{"ok":false,"said":"Nothing seems to be playing right now."}""")),
        )
        assertNull(PcMedia.said(obj("""{"ok":false,"error":"RuntimeError"}""")))
        assertNull(PcMedia.said(null))
        assertTrue(PcMedia.missing(ApiError.NotFound))
        assertFalse(PcMedia.missing(ApiError.BadToken))
    }

    @Test
    fun theMissingWordsAreThePcsOwn() {
        // jarvis_quick.MEDIA_MISSING, word for word.
        val py = listOf(File("../../backend/jarvis_quick.py"), File("../backend/jarvis_quick.py"))
            .firstOrNull { it.isFile }?.readText()?.replace(Regex("\"\\s*\\n\\s*\""), "")
        if (py != null) assertTrue(py.contains(PcMedia.MISSING))
    }
}
