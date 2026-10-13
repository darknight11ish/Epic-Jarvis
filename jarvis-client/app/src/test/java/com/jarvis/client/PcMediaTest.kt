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
     * The plate is drawn while a track is PLAYING or PAUSED, and for nothing
     * else. The owner first said "playing on pc shouldnt show up unless there
     * is something actively playing on the pc" (2026-10-13), and then chose
     * "Also show it while paused" when asked which he wanted. `GET /api/media`
     * sends only `{"ok", "said"}`, so the PC's own sentence is the whole
     * signal - these are its real shapes, word for word
     * (jarvis_media.now_playing).
     */
    @Test
    fun theTwoLoadedStatesAreShownAndNothingElseIs() {
        assertEquals(
            PcMedia.State.PLAYING,
            PcMedia.state("Playing: “Everything In Its Right Place” by Radiohead."),
        )
        assertEquals(PcMedia.State.PLAYING, PcMedia.state("Playing: “Untitled”."))
        assertEquals(PcMedia.State.PLAYING, PcMedia.state("Playing: something by Radiohead."))
        assertEquals(
            "a paused track SHOWS now - the owner's answer of 2026-10-13",
            PcMedia.State.PAUSED,
            PcMedia.state("Paused: “Everything In Its Right Place” by Radiohead."),
        )
        assertEquals(PcMedia.State.PAUSED, PcMedia.state("Paused: “Untitled”."))
        // Everything else hides the plate: the PC's own empty answer, a failed
        // or unreachable read, and anything this phone does not recognise.
        assertEquals("the empty answer must not draw the plate", PcMedia.State.NONE, PcMedia.state(PcMedia.NOTHING))
        assertEquals(PcMedia.State.NONE, PcMedia.state(null))
        assertEquals(PcMedia.State.NONE, PcMedia.state(""))
        assertEquals(PcMedia.State.NONE, PcMedia.state("   "))
        assertEquals(PcMedia.State.NONE, PcMedia.state("Done."))
        assertTrue(PcMedia.shown(PcMedia.State.PLAYING))
        assertTrue(PcMedia.shown(PcMedia.State.PAUSED))
        assertFalse("an idle PC must not draw the plate", PcMedia.shown(PcMedia.State.NONE))
    }

    /**
     * The transport reflects WHICH it is: a paused track offers Play and not
     * Pause. Without this the plate would show on pause with a Pause button
     * that can do nothing - the very dead control this work removed.
     */
    @Test
    fun theTransportReflectsWhetherItIsPlayingOrPaused() {
        assertEquals(listOf("previous", "pause", "next"), PcMedia.transport(PcMedia.State.PLAYING))
        assertEquals(listOf("previous", "play", "next"), PcMedia.transport(PcMedia.State.PAUSED))
        assertFalse(
            "the two states must not offer the same transport, or one button is always wrong",
            PcMedia.transport(PcMedia.State.PLAYING) == PcMedia.transport(PcMedia.State.PAUSED),
        )
        assertTrue(PcMedia.transport(PcMedia.State.NONE).isEmpty())
        // Every button offered is one the PC really takes, and exactly one of
        // play/pause is in each transport.
        for (state in listOf(PcMedia.State.PLAYING, PcMedia.State.PAUSED)) {
            assertTrue(PcMedia.transport(state).all { it in PcMedia.ACTIONS })
            val toggles = PcMedia.transport(state).filter { it == PcMedia.PLAY || it == PcMedia.PAUSE }
            assertEquals("$state must offer exactly one of play/pause", 1, toggles.size)
        }
    }

    /**
     * A button's own answer is NOT a description. `jarvis_media._SAID` answers
     * a control with "Playing.", "Paused.", "Skipped to the next." or "Back to
     * the previous." - none of which names a track or says what is playing, so
     * none of them may be read as a state. The plate reads the PC again after a
     * button for the descriptive sentence, and shows the button's words only
     * when they are NOT one of these (a refusal or a notice).
     */
    @Test
    fun aButtonsOwnAnswerIsNotAState() {
        assertEquals(
            setOf("Playing.", "Paused.", "Skipped to the next.", "Back to the previous."),
            PcMedia.ACKS,
        )
        for (answer in PcMedia.ACKS) {
            assertTrue("$answer should be an acknowledgement", PcMedia.ack(answer))
            assertEquals("$answer must never be read as a state", PcMedia.State.NONE, PcMedia.state(answer))
        }
        assertFalse("a description is not an acknowledgement", PcMedia.ack("Paused: “X”."))
        assertFalse(PcMedia.ack(PcMedia.NOTHING))
        assertFalse(PcMedia.ack(null))
        // And the sentence that DOES carry the paused state is the description,
        // not the acknowledgement - the distinction this test exists for.
        assertEquals(PcMedia.State.PAUSED, PcMedia.state("Paused: “X”."))
        assertEquals(PcMedia.State.NONE, PcMedia.state("Paused."))
    }
}
