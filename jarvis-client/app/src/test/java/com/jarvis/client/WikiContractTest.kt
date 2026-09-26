package com.jarvis.client

import com.jarvis.client.net.ApiError
import com.jarvis.client.net.JarvisJson
import com.jarvis.client.net.Wiki
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.int
import kotlinx.serialization.json.jsonObject
import kotlinx.serialization.json.jsonPrimitive
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test
import java.io.File

/**
 * The wiki builder's three routes, as the desktop really ANSWERS them, read
 * the way the phone does.
 *
 * The answers are `jarvis-desktop/tests/fixtures/wiki-cases.json` - the same
 * file the desktop's tests read - written by `tools/gen_wiki_cases.py` from
 * `backend/jarvis_wiki.py`'s own functions; `backend/test_wiki.py` fails
 * when it is stale. It is found by walking up from the test's working
 * folder (Gradle runs unit tests in `jarvis-client/app`), so there is one
 * copy, not two that can drift apart.
 */
class WikiContractTest {

    private val cases: JsonObject = run {
        var dir: File? = File(System.getProperty("user.dir") ?: ".").absoluteFile
        var found: File? = null
        while (dir != null && found == null) {
            val f = File(dir, "jarvis-desktop/tests/fixtures/wiki-cases.json")
            if (f.isFile) found = f
            dir = dir.parentFile
        }
        val file = requireNotNull(found) {
            "jarvis-desktop/tests/fixtures/wiki-cases.json not found above ${System.getProperty("user.dir")}"
        }
        (JarvisJson.parseToJsonElement(file.readText()) as JsonObject)["cases"]!!.jsonObject
    }

    private fun body(case: String): JsonObject = cases[case]!!.jsonObject["body"]!!.jsonObject

    private fun status(case: String): Int = cases[case]!!.jsonObject["status"]!!.jsonPrimitive.int

    @Test
    fun `the ready answer is read as the desktop sent it`() {
        val v = Wiki.read(body("status_ready"))
        assertTrue(v.available)
        assertTrue(v.folderOk)
        assertEquals(1, v.pages)
        assertEquals(
            listOf(
                "old-minutes.md" to "too_big", "planting-dates.md" to "changed",
                "plot-map.pdf" to "unreadable", "seed-list.txt" to "in_wiki",
                "spring-meeting.md" to "new",
            ),
            v.sources.map { it.name to it.state },
        )
        assertEquals(listOf("[2026-09-20] ingest | seed-list.txt"), v.recent.map(Wiki::logLine))
        v.sources.forEach { assertFalse("no words for ${it.state}", Wiki.label(it.state) == it.state) }
    }

    @Test
    fun `Add is offered for new and changed only, and only when it can run`() {
        val v = Wiki.read(body("status_ready"))
        assertEquals(listOf("planting-dates.md", "spring-meeting.md"),
            v.sources.filter { v.canAdd(it) }.map { it.name })
        val off = Wiki.read(body("status_off"))
        assertFalse(off.available)
        assertTrue(off.why.contains("second graphics card"))
        assertTrue(off.sources.none { off.canAdd(it) })
        val busy = Wiki.read(body("status_running"))
        assertEquals("spring-meeting.md", busy.runningSource)
        assertTrue(busy.sources.none { busy.canAdd(it) })
    }

    @Test
    fun `no wiki folder says what to make`() {
        val v = Wiki.read(body("status_no_wiki_folder"))
        assertFalse(v.folderOk)
        assertTrue(v.folderWhy.contains("Jarvis Wiki"))
    }

    @Test
    fun `each job state is said in the desktop words, and only done is done`() {
        val want = mapOf(
            "job_reading" to Pair(false, false),
            "job_waiting" to Pair(false, false),
            "job_done" to Pair(true, true),
            "job_denied" to Pair(true, false),
            "job_failed" to Pair(true, false),
            "job_model_refused" to Pair(true, false),
        )
        for ((case, finalDone) in want) {
            val said = Wiki.describe(body(case))
            assertEquals(case, finalDone.first, said.final)
            assertEquals(case, finalDone.second, said.done)
            assertEquals(case, body(case)["message"]!!.jsonPrimitive.content, said.text)
        }
        assertEquals("wiki_0000000000000000", Wiki.jobId(body("ingest_started")))
        assertEquals(202, status("ingest_started"))
    }

    @Test
    fun `an explained refusal is shown with its reason, never as added`() {
        for (case in listOf("ingest_in_wiki", "ingest_busy", "ingest_off", "ingest_too_big",
            "ingest_unreadable")) {
            val said = Wiki.describe(body(case))
            assertTrue(case, said.final)
            assertFalse(case, said.done)
            assertEquals(case, body(case)["error"]!!.jsonPrimitive.content, said.text)
        }
        assertEquals(409, status("ingest_in_wiki"))
        assertEquals(503, status("ingest_off"))
    }

    @Test
    fun `the request carries only the document name`() {
        val sent = JarvisJson.parseToJsonElement(Wiki.body(" spring-meeting.md ")!!).jsonObject
        assertEquals(setOf("source"), sent.keys)
        assertEquals("spring-meeting.md", sent["source"]!!.jsonPrimitive.content)
        assertEquals(null, Wiki.body("  "))
        assertEquals("/api/wiki/ingest?id=wiki_a%2Fb", Wiki.statusPath("wiki_a/b"))
    }

    @Test
    fun `an older desktop is told to update`() {
        assertTrue(Wiki.failure(ApiError.NotFound)!!.contains("apply-patches"))
        assertEquals(null, Wiki.failure(ApiError.BadToken))
    }
}
