package com.jarvis.client

import com.jarvis.client.net.ApiError
import com.jarvis.client.net.JarvisJson
import com.jarvis.client.net.StopEverything
import kotlinx.serialization.json.jsonObject
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test
import java.io.File

/**
 * "Stop everything" on the phone, held to the PC's `backend/jarvis_stop_all.py`
 * (the reply below is that module's own shape) and to the desktop's words.
 */
class StopEverythingTest {

    @Test
    fun thePcsOwnSentenceFollowsStoppedSpeaking() {
        val reply = JarvisJson.parseToJsonElement(
            """{"ok":true,"stopped":["The paused task was forgotten."],"problems":[],
               "message":"Stopped everything. The paused task was forgotten."}""",
        ).jsonObject
        assertEquals(
            "Stopped speaking. Stopped everything. The paused task was forgotten.",
            StopEverything.describe(reply, null),
        )
    }

    @Test
    fun nothingRunningIsSaidInThePcsWords() {
        val reply = JarvisJson.parseToJsonElement(
            """{"ok":true,"stopped":[],"message":"Nothing was running, so there was nothing to stop."}""",
        ).jsonObject
        assertEquals(
            "Stopped speaking. Nothing was running, so there was nothing to stop.",
            StopEverything.describe(reply, null),
        )
    }

    @Test
    fun aReplyWithoutWordsStillSaysSomething() {
        assertEquals("Stopped speaking. ${StopEverything.PC_SILENT}",
            StopEverything.describe(JarvisJson.parseToJsonElement("{}").jsonObject, null))
    }

    @Test
    fun anOlderPcIsToldApartFromADeadLink() {
        val old = StopEverything.describe(null, ApiError.NotFound)
        assertTrue(old, old.startsWith("Stopped speaking.") && "stop-all.patch" in old)
        val down = StopEverything.describe(null, ApiError.Unreachable("timeout"))
        assertTrue(down, down.startsWith("Stopped speaking. Nothing else could be stopped."))
        val token = StopEverything.describe(null, ApiError.BadToken)
        assertTrue(token, "nothing else was stopped" in token)
    }

    @Test
    fun anUnreachablePcIsSaidInPlainWordsWithItsButton() {
        // The audit's case: the raw "Failed to connect to /100.101.1.2 ..." and
        // the PC's private address on screen. Now the plain words and Try again.
        val raw = "Failed to connect to /100.101.1.2 (port 8765) from /100.64.3.4 (port 45678) after 10000ms"
        val e = ApiError.Unreachable(raw, "connect_timeout")
        val said = StopEverything.describe(null, e)
        assertEquals(
            "Stopped speaking. Nothing else could be stopped. Your PC isn't answering. It may be " +
                "asleep or switched off, or Tailscale or NordVPN Meshnet may be off at one end. Wake " +
                "the PC, check the private network on both, then try again.",
            said,
        )
        assertTrue(said, "100.101" !in said)
        val p = StopEverything.problem(e)!!
        assertEquals(said, p.text)
        assertEquals("Try again", p.button)
        // No address saved at all: the "not connected to a PC yet" words.
        val unpaired = StopEverything.problem(ApiError.Unreachable("No desktop address set", "not_paired"))!!
        assertEquals("Check the connection settings", unpaired.button)
        assertTrue(StopEverything.problem(ApiError.NotFound) == null)
    }

    @Test
    fun theSameWordsAsTheDesktop() {
        // The desktop's hotkey is called "Stop everything" in Settings and its
        // notification's title; the phone's button says the same.
        val hotkeys = listOf(File("../../jarvis-desktop/src-tauri/src/hotkeys.rs"),
            File("../jarvis-desktop/src-tauri/src/hotkeys.rs"),
            File("jarvis-desktop/src-tauri/src/hotkeys.rs")).firstOrNull { it.isFile }
        if (hotkeys != null) {
            assertTrue(hotkeys.readText().contains("label: \"${StopEverything.LABEL}\""))
        }
        assertEquals("Stop everything", StopEverything.LABEL)
        val commands = listOf(File("../../jarvis-desktop/src-tauri/src/commands.rs"),
            File("../jarvis-desktop/src-tauri/src/commands.rs"),
            File("jarvis-desktop/src-tauri/src/commands.rs")).firstOrNull { it.isFile }
        if (commands != null) {
            val rs = commands.readText()
            for (words in listOf(StopEverything.SPEECH, StopEverything.PC_SILENT, StopEverything.NOT_REACHED)) {
                assertTrue(words, rs.contains("\"$words\""))
            }
        }
    }
}
