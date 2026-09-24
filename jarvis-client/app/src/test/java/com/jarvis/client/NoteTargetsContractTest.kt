package com.jarvis.client

import com.jarvis.client.net.ApiError
import com.jarvis.client.net.JarvisJson
import com.jarvis.client.net.NoteCapture
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.jsonObject
import kotlinx.serialization.json.jsonPrimitive
import kotlinx.serialization.json.int
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test

/**
 * "Which note apps is the desktop set up for?" - `GET /api/notes/capture`
 * with no id - as the desktop really ANSWERS it, read the way the phone does.
 *
 * The answers come from `src/test/resources/contract/note-targets.json`,
 * which backend/test_obsidian_notes.py writes from `jarvis_note_capture`'s
 * own functions, one per setup, and checks is still what they produce.
 */
class NoteTargetsContractTest {

    private val fixture: JsonObject = run {
        val text = requireNotNull(javaClass.classLoader?.getResource("contract/note-targets.json")) {
            "contract/note-targets.json is missing - run backend/test_obsidian_notes.py --write"
        }.readText()
        JarvisJson.parseToJsonElement(text) as JsonObject
    }

    private fun body(case: String): JsonObject = fixture[case]!!.jsonObject["body"]!!.jsonObject

    private fun status(case: String): Int = fixture[case]!!.jsonObject["status"]!!.jsonPrimitive.int

    @Test
    fun `each setup is read as exactly the apps that are set up`() {
        assertEquals(NoteCapture.Targets.Known(listOf("logseq", "joplin", "obsidian")),
            NoteCapture.targets(body("all")))
        assertEquals(NoteCapture.Targets.Known(emptyList()), NoteCapture.targets(body("none")))
        assertEquals(NoteCapture.Targets.Known(listOf("logseq")), NoteCapture.targets(body("logseq_only")))
        assertEquals(NoteCapture.Targets.Known(listOf("obsidian")), NoteCapture.targets(body("obsidian_only")))
    }

    @Test
    fun `an older desktop is unknown, and the line says to update it`() {
        // It answers 404, which JarvisApi.probe turns into ApiError.NotFound.
        assertEquals(404, status("older_backend"))
        val t = NoteCapture.targetsFailure(ApiError.NotFound, "generic")
        assertTrue(NoteCapture.noTargetsLine(t).contains("apply-patches"))
        // And its body, if it were ever read as a list, is not one.
        assertTrue(NoteCapture.targets(body("older_backend")) is NoteCapture.Targets.Unknown)
    }

    @Test
    fun `nothing set up says so, rather than offering every app`() {
        val line = NoteCapture.noTargetsLine(NoteCapture.targets(body("none")))
        assertTrue(line.startsWith("No note app is set up on your PC"))
    }

    @Test
    fun `obsidian is filed as obsidian, and named as Obsidian`() {
        val sent = JarvisJson.parseToJsonElement(NoteCapture.body("obsidian", "x")!!).jsonObject
        assertEquals("obsidian", sent["target"]!!.jsonPrimitive.content)
        assertEquals("Obsidian", NoteCapture.name("obsidian"))
    }
}
