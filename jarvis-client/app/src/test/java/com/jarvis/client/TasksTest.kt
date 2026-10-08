package com.jarvis.client

import com.jarvis.client.net.ApiError
import com.jarvis.client.net.ApiResult
import com.jarvis.client.net.JarvisJson
import com.jarvis.client.net.Tasks
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.jsonArray
import kotlinx.serialization.json.jsonObject
import kotlinx.serialization.json.jsonPrimitive
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test

/**
 * The job list on the Brain screen, read from what the PC REALLY answers.
 *
 * `contract/tasks-cases.json` is written by tools/gen_tasks_cases.py: it builds
 * a real `jarvis_tasks.JobList`, puts jobs into real states through the
 * module's own calls, and writes down exactly what `status()` returned -
 * byte for byte the file the desktop builds against. Nothing in it is
 * hand-made, so a change to the payload has to be a decision.
 *
 * The last test is the privacy one. `status()` is counted only, so the fixture
 * has a case whose rows carry a `title` the client was never sent; if the
 * screen ever rendered a field it is not given, that case would catch it.
 */
class TasksTest {

    private val cases: JsonObject = run {
        val text = requireNotNull(javaClass.classLoader?.getResource("contract/tasks-cases.json")) {
            "contract/tasks-cases.json is missing - run tools/gen_tasks_cases.py"
        }.readText()
        (JarvisJson.parseToJsonElement(text) as JsonObject)["cases"]!!.jsonObject
    }

    private fun loaded(name: String): Tasks.Answer {
        val read = Tasks.readOf(ApiResult.Ok(cases[name]!!.jsonObject["answer"]!!.jsonObject))
        assertTrue("$name should load", read is Tasks.Read.Loaded)
        return (read as Tasks.Read.Loaded).answer
    }

    @Test
    fun `the real answer is read, and its counts match its rows`() {
        val expect = cases["mixed"]!!.jsonObject["expect"]!!.jsonObject
        val answer = loaded("mixed")
        assertEquals(expect["waiting"]!!.jsonPrimitive.content.toInt(), answer.waiting)
        assertEquals(expect["running"]!!.jsonPrimitive.content.toInt(), answer.running)
        assertEquals(expect["blocked"]!!.jsonPrimitive.content.toInt(), answer.blocked)
        assertEquals(expect["rows"]!!.jsonPrimitive.content.toInt(), answer.rows.size)
        assertEquals(
            expect["states"]!!.jsonArray.map { it.jsonPrimitive.content }.sorted(),
            answer.rows.map { it.state }.sorted(),
        )
        // The headline counts what the PC sent, never what the screen guesses.
        assertTrue(answer.headline()!!.contains("1 running"))
        assertNull(Tasks.readLine(Tasks.Read.Loaded(answer)))
    }

    @Test
    fun `a job says how far it got and which tools it will use`() {
        val row = loaded("mixed").rows.first { it.state == "running" }
        assertEquals(2, row.step)
        assertEquals(3, row.steps)
        assertEquals(listOf("web_search", "send_email", "notes_write"), row.tools)
        assertEquals("step 2 of 3 - web_search, send_email, notes_write", row.shape())
    }

    @Test
    fun `a blocked job shows the PC's own sentence and offers Retry only`() {
        val row = loaded("mixed").rows.first { it.needsAttention }
        assertEquals("blocked", row.state)
        assertTrue(row.question.contains("was part-way through"))
        assertEquals(listOf("retry"), Tasks.actsFor(row.state))
    }

    @Test
    fun `the steers offered match the state, and nothing else`() {
        // The four the PC accepts, and never a fifth.
        assertEquals(listOf("pause", "cancel"), Tasks.actsFor("running"))
        assertEquals(listOf("pause", "cancel"), Tasks.actsFor("queued"))
        assertEquals(listOf("pause", "cancel"), Tasks.actsFor("waiting_approval"))
        assertEquals(listOf("resume", "cancel"), Tasks.actsFor("paused"))
        assertEquals(listOf("retry"), Tasks.actsFor("failed"))
        assertEquals(listOf("retry"), Tasks.actsFor("cancelled"))
        assertTrue(Tasks.actsFor("succeeded").isEmpty())
        assertTrue(Tasks.actsFor("nonsense").isEmpty())
        for (state in listOf("queued", "running", "waiting_approval", "waiting_input",
                             "paused", "scheduled", "blocked", "succeeded", "failed",
                             "cancelled")) {
            assertTrue(state, Tasks.actsFor(state).all { it in Tasks.ACTS })
        }
    }

    @Test
    fun `every state the backend can send has words, not an underscore`() {
        // backend/jarvis_tasks.py's own STATES tuple.
        for (state in listOf("queued", "running", "waiting_approval", "waiting_input",
                             "paused", "scheduled", "blocked", "succeeded", "failed",
                             "cancelled")) {
            val words = Tasks.stateWords(state)
            assertFalse(state, words.contains("_"))
            assertTrue(state, words.isNotBlank())
        }
        assertEquals("waiting", Tasks.stateWords("queued"))
        assertEquals("needs you", Tasks.stateWords("blocked"))
        assertEquals("done", Tasks.stateWords("succeeded"))
    }

    @Test
    fun `an empty list is empty, not an error`() {
        val answer = loaded("empty")
        assertEquals(0, answer.rows.size)
        assertNull(answer.headline())
    }

    @Test
    fun `an older backend is told to update, in words`() {
        assertEquals(Tasks.Read.OlderBackend, Tasks.readOf(ApiResult.Failed(ApiError.NotFound)))
        assertEquals(Tasks.Read.OlderBackend, Tasks.readOf(ApiResult.Failed(ApiError.NotAvailable)))
        assertEquals(Tasks.UPDATE, Tasks.readLine(Tasks.Read.OlderBackend))
        val odd = Tasks.readOf(ApiResult.Ok(JsonObject(emptyMap())))
        assertTrue(odd is Tasks.Read.Failed)
    }

    @Test
    fun `a conflict is not already handled elsewhere`() {
        // On approve/deny a 409 means "someone else answered it". Here it means
        // the job was not in the state the button assumed.
        assertEquals(Tasks.NOT_IN_THAT_STATE, Tasks.failure(ApiError.AlreadyHandled))
        assertEquals(Tasks.UPDATE, Tasks.failure(ApiError.NotFound))
        assertNull(Tasks.failure(ApiError.BadToken))
    }

    @Test
    fun `the two bodies are what the PC's routes parse`() {
        assertEquals("""{"id":"job-1","act":"pause"}""", Tasks.actBody("job-1", "pause"))
        assertEquals("""{"id":"job-2","act":"retry"}""", Tasks.actBody("job-2", "retry"))
        // A quote in an id cannot break out of the JSON.
        assertTrue(Tasks.actBody("""a"b""", "cancel").startsWith("""{"id":"a\"b""""))
        // The answer is trimmed, and a blank one is not sent at all.
        assertEquals("""{"id":"job-1","answer":"order 4471"}""",
            Tasks.inputBody("job-1", "  order 4471  "))
        assertNull(Tasks.inputBody("job-1", "   "))
        assertTrue(Tasks.inputBody("job-1", """a"b""")!!.contains("""a\"b"""))
        assertEquals("/api/tasks/input", Tasks.INPUT_PATH)
    }

    @Test
    fun `the reply is counted only - a title we were never sent is not shown`() {
        val answer = loaded("title_is_ignored")
        assertEquals(loaded("mixed").rows.size, answer.rows.size)
        // Nothing the client holds can carry it: the row has no title field,
        // and its own text comes from the PC's state, step count and tools.
        for (row in answer.rows) {
            assertFalse(row.shape(), row.shape().contains("SECRET TITLE"))
            assertFalse(row.question, row.question.contains("SECRET TITLE"))
            assertFalse(row.toString(), row.toString().contains("SECRET TITLE"))
        }
        assertFalse(answer.headline().orEmpty().contains("SECRET TITLE"))
    }

    @Test
    fun `the labels are the desktop's`() {
        assertEquals("Job list", Tasks.HEADING)
        assertEquals("/api/tasks", Tasks.PATH)
        assertEquals("/api/tasks/act", Tasks.ACT_PATH)
        assertEquals(listOf("pause", "resume", "cancel", "retry"), Tasks.ACTS)
        assertEquals("Cancel", Tasks.actWords("cancel"))
    }
}
