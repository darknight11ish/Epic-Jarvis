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

    /**
     * The plate is drawn only while a track is ACTUALLY PLAYING (the owner,
     * 2026-10-13). `GET /api/media` sends only `{"ok", "said"}`, so these are
     * the three sentences jarvis_media.now_playing can really produce, plus
     * the failed and the unrecognised cases - and every one but the first has
     * to come back false, or the plate is on screen while nothing plays.
     */
    @Test
    fun onlyAReallyPlayingTrackCounts() {
        // The PC's own three shapes, word for word (jarvis_media.now_playing).
        assertTrue(PcMedia.playing("Playing: “Everything In Its Right Place” by Radiohead."))
        assertTrue(PcMedia.playing("Playing: “Untitled”."))
        assertTrue(PcMedia.playing("Playing: something by Radiohead."))
        assertFalse(
            "a paused track is not actively playing - the owner's words",
            PcMedia.playing("Paused: “Everything In Its Right Place” by Radiohead."),
        )
        assertFalse(
            "the empty answer must not draw the plate",
            PcMedia.playing(PcMedia.NOTHING),
        )
        // Failed and unknown reads claim nothing.
        assertFalse(PcMedia.playing(null))
        assertFalse(PcMedia.playing(""))
        assertFalse(PcMedia.playing("   "))
        assertFalse(PcMedia.playing("Done."))
        // CONTROL: the gate is not simply "any sentence is true" - the three
        // shapes above are distinguished, and the prefix is what decides.
        assertTrue(PcMedia.PLAYING_PREFIX.startsWith("Playing"))
        assertFalse(PcMedia.PAUSED_PREFIX == PcMedia.PLAYING_PREFIX)
    }
}
