package com.jarvis.client

import com.jarvis.client.net.ApiError
import com.jarvis.client.net.JarvisJson
import com.jarvis.client.net.NoteCapture
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.jsonObject
import kotlinx.serialization.json.jsonPrimitive
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test

/**
 * The phone's quick note, held to the desktop's `backend/note-capture.patch`
 * (`jarvis_note_capture.capture` / `capture_status`): the shapes below are
 * that code's job records, not guesses.
 */
class NoteCaptureTest {

    private fun job(json: String): JsonObject = JarvisJson.parseToJsonElement(json).jsonObject

    @Test
    fun theBodyCarriesTheTargetAndTheWordsSafely() {
        val body = NoteCapture.body("joplin", "  say \"hi\"\nthen go  ")!!
        val parsed = JarvisJson.parseToJsonElement(body).jsonObject
        assertEquals("joplin", parsed["target"]!!.jsonPrimitive.content)
        assertEquals("say \"hi\"\nthen go", parsed["text"]!!.jsonPrimitive.content)
    }

    @Test
    fun anythingButJoplinIsTheJournal() {
        val parsed = JarvisJson.parseToJsonElement(NoteCapture.body("LOG", "x")!!).jsonObject
        assertEquals("logseq", parsed["target"]!!.jsonPrimitive.content)
    }

    @Test
    fun anEmptyNoteIsNotSent() {
        assertNull(NoteCapture.body("logseq", "   "))
    }

    @Test
    fun filedIsSaidOnlyForStateFiledInTheDesktopsWords() {
        val said = NoteCapture.describe(
            job("""{"id":"note_1","state":"filed","message":"Filed in Logseq, journals/2026_09_23.md."}"""),
            "logseq",
        )
        assertTrue(said.filed && said.final)
        assertEquals("Filed in Logseq, journals/2026_09_23.md.", said.text)
    }

    @Test
    fun waitingIsNotFinalAndNotFiled() {
        val said = NoteCapture.describe(job("""{"id":"n","state":"waiting","message":"Filed?"}"""), "joplin")
        assertFalse(said.final)
        assertFalse(said.filed)
        assertTrue(said.text.contains("Waiting for your approval"))
    }

    @Test
    fun aRefusalCarriesTheDesktopsReason() {
        val said = NoteCapture.describe(
            job("""{"state":"not_filed","message":"You said no, so nothing was written."}"""), "logseq",
        )
        assertTrue(said.final)
        assertFalse(said.filed)
        assertEquals("You said no, so nothing was written.", said.text)
    }

    @Test
    fun anUnknownStateIsNeverShownAsFiled() {
        assertFalse(NoteCapture.describe(job("""{"state":"weird"}"""), "logseq").filed)
        assertFalse(NoteCapture.describe(job("""{}"""), "logseq").filed)
    }

    @Test
    fun theStatusAddressEncodesTheId() {
        assertEquals("/api/notes/capture?id=note_a%2Fb", NoteCapture.statusPath("note_a/b"))
    }

    @Test
    fun aMissingRouteNamesThePatch() {
        assertTrue(NoteCapture.failure(ApiError.NotFound)!!.contains("note-capture"))
        assertNull(NoteCapture.failure(ApiError.BadToken))
    }
}
