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
        assertTrue(down, down.startsWith("Stopped speaking.") && "could not be reached" in down)
        val token = StopEverything.describe(null, ApiError.BadToken)
        assertTrue(token, "nothing else was stopped" in token)
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
    }
}
