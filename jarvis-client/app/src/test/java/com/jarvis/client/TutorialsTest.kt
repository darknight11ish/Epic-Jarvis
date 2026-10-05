package com.jarvis.client

import com.jarvis.client.net.ApiError
import com.jarvis.client.net.ApiResult
import com.jarvis.client.net.JarvisJson
import com.jarvis.client.net.Tutorials
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.jsonObject
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test

/**
 * "Tutorials" and the FAQ on the Brain screen (docs/JARVIS-API.md section 114).
 *
 * The answers below are the shapes `GET /api/tutorials`, `POST
 * /api/tutorials/progress` and `GET /api/faq` really give (backend/
 * jarvis_tutorials.py), written out here rather than generated, because what is
 * being checked is the READING of them: which section a tutorial lands in, where
 * the owner resumes, what a state says in words, and what a bad answer does.
 * backend/test_tutorials.py owns the catalogue's own content and the desktop's
 * suite owns the desktop's half; this is the phone's.
 */
class TutorialsTest {

    private fun json(text: String): JsonObject =
        JarvisJson.parseToJsonElement(text).jsonObject

    private val catalogue = json(
        """
        {"ok": true,
         "sections": [{"id": "pc", "title": "On this PC"},
                      {"id": "phone", "title": "On your phone"}],
         "tutorials": [
           {"id": "intro", "section": "both", "title": "What Jarvis is", "why": "why",
            "minutes": 2, "steps": [{"title": "one", "body": "b", "where": "Brain"},
                                    {"title": "two", "body": "b", "where": "Brain"},
                                    {"title": "three", "body": "b", "where": "Brain"}],
            "state": "not_started", "step": 0, "steps_total": 3, "done": false,
            "resume_at": null, "due": true},
           {"id": "memory", "section": "both", "title": "What Jarvis remembers", "why": "why",
            "minutes": 3, "steps": [{"title": "one", "body": "b", "where": "Brain"},
                                    {"title": "two", "body": "b", "where": "Brain"},
                                    {"title": "three", "body": "b", "where": "Brain"}],
            "state": "in_progress", "step": 2, "steps_total": 3, "done": false,
            "resume_at": 2, "due": false},
           {"id": "pc-at-a-glance", "section": "pc", "title": "The desktop at a glance",
            "why": "why", "minutes": 2, "steps": [{"title": "one", "body": "b", "where": "HUD"}],
            "state": "done", "step": 1, "steps_total": 1, "done": true,
            "resume_at": null, "due": false},
           {"id": "phone-pairing", "section": "phone", "title": "Pairing your phone",
            "why": "why", "minutes": 3, "steps": [{"title": "one", "body": "b", "where": "Brain"}],
            "state": "skipped", "step": 0, "steps_total": 1, "done": false,
            "resume_at": null, "due": false}
         ]}
        """.trimIndent()
    )

    @Test
    fun `the catalogue is read, with the owner's place in each tutorial`() {
        val read = Tutorials.readOf(ApiResult.Ok(catalogue))
        assertTrue(read is Tutorials.Read.Loaded)
        val loaded = (read as Tutorials.Read.Loaded).catalogue
        assertEquals(listOf("pc", "phone"), loaded.sections)
        assertEquals(4, loaded.tutorials.size)
        val memory = loaded.tutorials.first { it.id == "memory" }
        assertEquals(2, memory.resumeAt)
        assertEquals(3, memory.stepsTotal)
        assertEquals(3, memory.steps.size)
        assertEquals("Brain", memory.steps.first().where)
        assertNull(Tutorials.readLine(read))
    }

    @Test
    fun `a section is its own tutorials plus the shared ones, which is the point`() {
        val loaded = (Tutorials.readOf(ApiResult.Ok(catalogue)) as Tutorials.Read.Loaded).catalogue
        assertEquals(
            listOf("intro", "memory", "pc-at-a-glance"),
            loaded.forSection("pc").map { it.id },
        )
        assertEquals(
            listOf("intro", "memory", "phone-pairing"),
            loaded.forSection("phone").map { it.id },
        )
    }

    @Test
    fun `quitting and resuming, the recorded step is the one offered`() {
        val loaded = (Tutorials.readOf(ApiResult.Ok(catalogue)) as Tutorials.Read.Loaded).catalogue
        assertEquals(2, loaded.tutorials.first { it.id == "memory" }.startIndex)
        assertEquals(0, loaded.tutorials.first { it.id == "intro" }.startIndex)
        // A resume point past the end is ignored, not trusted.
        assertEquals(0, loaded.tutorials.first { it.id == "memory" }.copy(resumeAt = 99).startIndex)
    }

    @Test
    fun `each state says where the owner is, in the desktop's words`() {
        val loaded = (Tutorials.readOf(ApiResult.Ok(catalogue)) as Tutorials.Read.Loaded).catalogue
        assertEquals(Tutorials.NOT_STARTED, loaded.tutorials.first { it.id == "intro" }.stateWords)
        assertEquals("${Tutorials.RESUME} 3", loaded.tutorials.first { it.id == "memory" }.stateWords)
        assertEquals(Tutorials.DONE, loaded.tutorials.first { it.id == "pc-at-a-glance" }.stateWords)
        assertEquals(Tutorials.SKIPPED, loaded.tutorials.first { it.id == "phone-pairing" }.stateWords)
    }

    @Test
    fun `a finished or skipped tutorial is offered again, a fresh one is not`() {
        val loaded = (Tutorials.readOf(ApiResult.Ok(catalogue)) as Tutorials.Read.Loaded).catalogue
        assertTrue(loaded.tutorials.first { it.id == "pc-at-a-glance" }.showsAgain)
        assertTrue(loaded.tutorials.first { it.id == "phone-pairing" }.showsAgain)
        assertFalse(loaded.tutorials.first { it.id == "intro" }.showsAgain)
    }

    @Test
    fun `next stops at the last step and back stops at the first`() {
        val loaded = (Tutorials.readOf(ApiResult.Ok(catalogue)) as Tutorials.Read.Loaded).catalogue
        val intro = loaded.tutorials.first { it.id == "intro" }
        assertEquals(1, intro.nextIndex(0))
        assertEquals(2, intro.nextIndex(1))
        assertNull(intro.nextIndex(2))
        assertNull(intro.backIndex(0))
        assertEquals(1, intro.backIndex(2))
        assertEquals("${Tutorials.STEP_OF} 2 ${Tutorials.OF} 3", intro.copy(step = 1).stepWords)
    }

    @Test
    fun `an older backend is told to update, in words`() {
        assertEquals(Tutorials.Read.OlderBackend, Tutorials.readOf(ApiResult.Failed(ApiError.NotFound)))
        assertEquals(Tutorials.Read.OlderBackend, Tutorials.readOf(ApiResult.Failed(ApiError.NotAvailable)))
        assertEquals(Tutorials.UPDATE, Tutorials.readLine(Tutorials.Read.OlderBackend))
        // The route saying `available: false` is the same thing.
        assertEquals(
            Tutorials.Read.OlderBackend,
            Tutorials.readOf(ApiResult.Ok(json("""{"available": false, "why": "not yet"}"""))),
        )
    }

    @Test
    fun `an answer that is not the shape this screen reads is answered in words`() {
        assertNull(Tutorials.parse(json("""{"ok": true, "tutorials": []}""")))
        assertNull(Tutorials.parse(json("""{"nope": 1}""")))
        val read = Tutorials.readOf(ApiResult.Ok(json("""{"ok": true, "nope": 1}""")))
        assertTrue(read is Tutorials.Read.Failed)
        assertTrue((read as Tutorials.Read.Failed).reason.startsWith("Your PC answered"))
        assertEquals(read.reason, Tutorials.readLine(read))
    }

    @Test
    fun `the FAQ is read, and searched in the question and the answer`() {
        val faq = json(
            """
            {"ok": true, "count": 2, "questions": [
              {"q": "Does Jarvis send my things anywhere?", "a": "Only the named exceptions.",
               "where": "What asks first"},
              {"q": "How do I make it forget something?", "a": "Erase the words wipes the text.",
               "where": "Brain - Memory"}
            ]}
            """.trimIndent()
        )
        val questions = Tutorials.parseFaq(faq)
        assertEquals(2, questions?.size)
        assertEquals("How do I make it forget something?", Tutorials.search(questions!!, "forget").single().q)
        // A word from the ANSWER works too - half the time that is what is remembered.
        assertEquals("How do I make it forget something?", Tutorials.search(questions, "wipe").single().q)
        assertEquals(2, Tutorials.search(questions, "").size)
        assertTrue(Tutorials.search(questions, "zzz").isEmpty())
        assertNull(Tutorials.parseFaq(json("""{"ok": true}""")))
        assertNull(Tutorials.parseQuestion(json("""{"a": "no question"}""")))
    }

    @Test
    fun `a step writes exactly what the route wants`() {
        val body = Tutorials.progressBody("memory", 2)
        assertEquals("memory", body["id"].toString().trim('"'))
        assertEquals("in_progress", body["state"].toString().trim('"'))
        assertEquals(2, body["step"].toString().toInt())
        val cleared = Tutorials.progressBody("memory", 0, "not_started")
        assertEquals("not_started", cleared["state"].toString().trim('"'))
    }

    @Test
    fun `the labels are the desktop's, word for word`() {
        // jarvis-desktop/tests/tutorials.mjs checks the same words the other way
        // round; backend/test_tutorials.py checks the sections and states.
        assertEquals("Tutorials", Tutorials.HEADING)
        assertEquals("Next", Tutorials.NEXT)
        assertEquals("Back", Tutorials.BACK)
        assertEquals("Skip this one", Tutorials.SKIP)
        assertEquals("Leave it here", Tutorials.QUIT)
        assertEquals("Show this one again", Tutorials.AGAIN)
        assertEquals(listOf("pc", "phone"), Tutorials.SECTIONS.map { it.first })
        assertEquals(listOf("in_progress", "done", "skipped", "not_started"), Tutorials.STATES)
    }
}
