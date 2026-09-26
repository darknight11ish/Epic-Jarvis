package com.jarvis.client

import com.jarvis.client.net.ApiError
import com.jarvis.client.net.ApiResult
import com.jarvis.client.net.BigModel
import com.jarvis.client.net.PlainErrors
import com.jarvis.client.net.JarvisJson
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.boolean
import kotlinx.serialization.json.int
import kotlinx.serialization.json.jsonObject
import kotlinx.serialization.json.jsonPrimitive
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNotNull
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test

/**
 * The Mind screen's "Big model (slow)" and "Deep questions" plates, read from
 * what the PC REALLY answers.
 *
 * `contract/big-model-cases.json` is the real output of
 * backend/jarvis_big_model.py - `GET /api/big-model` (`status_*`),
 * `GET /api/deep` (`deep_*`), and the POST answers (`post_*`, `ask_*`, each
 * `{"status", "body"}`) - written by tools/gen_big_model_cases.py, the same
 * file the desktop builds against. Nothing here is a shape typed to suit
 * this client.
 */
class BigModelContractTest {

    private val cases: JsonObject = run {
        val text = requireNotNull(javaClass.classLoader?.getResource("contract/big-model-cases.json")) {
            "contract/big-model-cases.json is missing - run tools/gen_big_model_cases.py"
        }.readText()
        (JarvisJson.parseToJsonElement(text) as JsonObject)["cases"]!!.jsonObject
    }

    private fun names(prefix: String) = cases.keys.filter { it.startsWith(prefix) }.sorted()

    private fun status(case: String): BigModel.Status =
        requireNotNull(BigModel.parse(cases[case]!!.jsonObject)) { "$case did not parse" }

    private fun deep(case: String): BigModel.Deep =
        requireNotNull(BigModel.parseDeep(cases[case]!!.jsonObject)) { "$case did not parse" }

    private fun code(case: String): Int = cases[case]!!.jsonObject["status"]!!.jsonPrimitive.int

    private fun body(case: String): JsonObject = cases[case]!!.jsonObject["body"]!!.jsonObject

    private fun job(s: BigModel.Status, id: String) = BigModel.switches(s).first { it.id == id }

    // ------------------------------------------------------------- status --

    /** AP-6: `last` as jarvis_big_model.py's status() sends it (fix-b2), added to a real case. */
    private fun withLast(case: String, last: String): BigModel.Status {
        val obj = cases[case]!!.jsonObject.toMutableMap()
        obj["last"] = JarvisJson.parseToJsonElement(last)
        return requireNotNull(BigModel.parse(JsonObject(obj)))
    }

    @Test
    fun `how the last card ended is said under its switch, and nothing when absent`() {
        val denied = withLast(
            "status_ready_off",
            """{"feature": "master", "outcome": "denied",
                "why": "You said no, so The big model stays off.", "at": 1800000000}""",
        )
        assertEquals("You said no, so The big model stays off.", BigModel.master(denied).lastLine)
        BigModel.switches(denied).forEach { assertNull(it.id, it.lastLine) }

        val failed = withLast("status_on_idle", """{"feature": "wiki", "outcome": "enabled", "why": "x"}""")
        assertNull("turned on is not news", job(failed, BigModel.WIKI).lastLine)

        val pending = withLast("status_pending", """{"feature": "master", "outcome": "timed_out", "why": "Old."}""")
        assertNull("a newer card waits", BigModel.master(pending).lastLine)

        for (name in names("status_")) {
            val s = status(name)
            assertNull(name, BigModel.master(s).lastLine)
            BigModel.switches(s).forEach { assertNull("$name ${it.id}", it.lastLine) }
        }
    }

    @Test
    fun `every case in the file is one this test knows the kind of`() {
        val kinds = listOf("status_", "deep_", "post_", "ask_")
        cases.keys.forEach { name -> assertTrue(name, kinds.any { name.startsWith(it) }) }
        assertEquals(13, names("status_").size)
        assertEquals(6, names("deep_").size)
        assertEquals(3, names("post_").size)
        assertEquals(4, names("ask_").size)
    }

    @Test
    fun `every status case is read, with both jobs and every line said`() {
        for (name in names("status_")) {
            val s = status(name)
            assertEquals(name, listOf(BigModel.WIKI, BigModel.DEEP), s.jobs.map { it.id })
            val master = BigModel.master(s)
            assertTrue("$name: a line under the main switch", master.line.isNotBlank())
            BigModel.switches(s).forEach {
                assertTrue("$name ${it.id}: a line under it", it.line.isNotBlank())
                assertFalse("$name ${it.id}: one full stop", it.line.endsWith(".."))
                assertNotNull("$name ${it.id}: which model", it.modelLine)
            }
            assertEquals(name, 3, BigModel.foundLines(s).size)
            BigModel.foundLines(s).forEach { assertTrue("$name: $it", it.isNotBlank() && !it.endsWith("..")) }
            assertTrue(name, BigModel.modelViews(s).isNotEmpty())
            BigModel.modelViews(s).forEach { assertTrue("$name ${it.title}", it.why.isNotBlank()) }
            assertTrue(name, BigModel.engineLine(s).isNotBlank())
            // The PC's "not verified" sentence is always there to show.
            assertTrue(name, s.unverified.contains("None of colibri's speed figures have been checked"))
            assertEquals(name, 2, BigModel.speedLines(s).size)
        }
    }

    @Test
    fun `not capable - nothing can be switched on, and it says why`() {
        for (name in listOf("status_not_installed", "status_no_python", "status_model_folder_missing")) {
            val s = status(name)
            assertFalse(name, s.found.capable)
            val master = BigModel.master(s)
            assertFalse(name, master.on)
            assertFalse("$name: the main switch is not offered", master.canTurnOn)
            assertTrue(name, master.line.contains(s.found.why))
            assertTrue(name, BigModel.summaryLine(s).startsWith("Not ready yet: "))
            BigModel.switches(s).forEach {
                assertFalse("$name ${it.id}", it.canTurnOn)
                assertTrue("$name ${it.id}", it.line.startsWith("Needs the big model set up"))
            }
        }
        assertTrue(BigModel.foundLines(status("status_not_installed"))[0].contains("no coli.cmd in that folder"))
        // Python is not checked until colibri is found; the line still has a subject.
        assertEquals(
            "Python 3: not checked (colibri first).",
            BigModel.foundLines(status("status_not_installed"))[1],
        )
        assertTrue(BigModel.foundLines(status("status_no_python"))[1].startsWith("Python 3 was not found"))
        val missing = BigModel.modelViews(status("status_model_folder_missing")).single()
        assertTrue(missing.why, missing.why.startsWith("The folder D:\\models\\qwen36_i4_gs64 does not exist"))
        assertTrue(missing.detail, missing.detail.contains("drive type unknown"))
        assertTrue(missing.detail, missing.detail.contains("free space on the drive not known"))
    }

    @Test
    fun `capable and off - only the main switch can be asked for`() {
        val s = status("status_ready_off")
        assertTrue(s.found.capable)
        assertEquals(
            "Ready: colibri and Python 3 found; usable: Qwen3.6-35B-A3B (medium), DeepSeek V4 Flash (giant).",
            BigModel.summaryLine(s),
        )
        val master = BigModel.master(s)
        assertTrue(master.canTurnOn)
        assertEquals("Off. Turn this on first, then the jobs you want.", master.line)
        BigModel.switches(s).forEach {
            assertFalse(it.id, it.canTurnOn)
            assertEquals(it.id, "Off. Turn on the big model itself first.", it.line)
        }
        assertEquals("Memory: 31.9 GB in this PC, 25.3 GB free right now.", BigModel.foundLines(s)[2])
        val (medium, giant) = BigModel.modelViews(s)
        assertEquals("Qwen3.6-35B-A3B (medium)", medium.title)
        assertEquals(
            "On D:, SATA SSD: 3,100 GB free on the drive; needs about 24 GB of memory while it runs.",
            medium.detail,
        )
        assertEquals("On E:, NVMe: 290 GB free on the drive; needs about 16 GB of memory while it runs.", giant.detail)
        assertEquals("Model: DeepSeek V4 Flash (giant, E:, NVMe).", job(s, BigModel.DEEP).modelLine)
        assertEquals(
            "Not running - it starts only when a background job needs it.",
            BigModel.engineLine(s),
        )
        assertEquals(BigModel.CPU_ONLY, BigModel.cudaLine(s))
    }

    @Test
    fun `a card waiting - the second card's words, and no second ask`() {
        val s = status("status_pending")
        assertEquals(listOf(BigModel.MASTER), s.pending)
        val master = BigModel.master(s)
        assertTrue(master.waiting)
        assertFalse(master.on)
        assertEquals("Waiting for your approval. Approve it on your PC or on this phone's Home screen.", master.line)
        assertFalse(master.canTurnOn)
        BigModel.switches(s).forEach { assertFalse(it.id, it.canTurnOn) }
    }

    @Test
    fun `on and idle - both jobs on, colibri starts when a job needs it`() {
        val s = status("status_on_idle")
        assertTrue(BigModel.master(s).on)
        assertEquals("On.", BigModel.master(s).line)
        BigModel.switches(s).forEach {
            assertTrue(it.id, it.on)
            assertFalse("${it.id}: already on", it.canTurnOn)
            assertTrue(it.line, it.line.contains("starts when this job next has work"))
        }
    }

    @Test
    fun `loading and running - the engine line says which, in the PC's words`() {
        val loading = status("status_loading")
        assertTrue(BigModel.engineLine(loading), BigModel.engineLine(loading).startsWith("Loading DeepSeek V4 Flash from E:"))
        assertTrue(BigModel.engineLine(loading).contains("this can take several minutes"))
        assertEquals("On. DeepSeek V4 Flash is loading.", job(loading, BigModel.DEEP).line)

        val running = status("status_running")
        assertTrue(BigModel.engineLine(running), BigModel.engineLine(running).startsWith("Running DeepSeek V4 Flash on 127.0.0.1:8765"))
        assertEquals("Working: DeepSeek V4 Flash is loaded.", job(running, BigModel.DEEP).line)
        assertEquals("Off.", job(running, BigModel.WIKI).line)
        // Master on, capable, model there: the wiki switch can be asked for.
        assertTrue(job(running, BigModel.WIKI).canTurnOn)
    }

    @Test
    fun `not enough free memory - on, but waiting, and the engine says what to close`() {
        val s = status("status_not_enough_free_memory")
        val line = BigModel.engineLine(s)
        assertTrue(line, line.startsWith("Stopped with a problem: not started: Qwen3.6-35B-A3B needs 24 GB"))
        BigModel.switches(s).forEach { assertTrue(it.id, it.on) }
        // The PC sends "... or wait.." here; the phone shows one full stop.
        assertTrue(job(s, BigModel.DEEP).line.endsWith("Close something big, or wait."))
        BigModel.modelViews(s).forEach { assertTrue(it.why, it.why.startsWith("Usable, but not right now")) }
    }

    @Test
    fun `too little memory in total and a giant model on SATA are both said`() {
        val small = status("status_too_little_memory")
        assertEquals("Memory: 16 GB in this PC, 11 GB free right now.", BigModel.foundLines(small)[2])
        assertTrue(BigModel.modelViews(small)[0].why.startsWith("This PC has 16 GB of memory"))

        val sata = BigModel.modelViews(status("status_giant_on_sata")).single()
        val warning = requireNotNull(sata.warning)
        assertTrue(warning, warning.contains("keep it on the NVMe drive"))
        // No other case carries a warning.
        for (name in names("status_") - "status_giant_on_sata") {
            BigModel.modelViews(status(name)).forEach { assertNull("$name ${it.title}", it.warning) }
        }
    }

    @Test
    fun `the graphics-card setting on without a capable second card is said`() {
        val s = status("status_cuda_refused")
        val cuda = BigModel.cudaLine(s)
        assertTrue(cuda, cuda.startsWith("Graphics card: [big_model] cuda is \"on\", but there is no capable second card"))
        assertTrue(BigModel.engineLine(s).startsWith("Stopped with a problem: "))
    }

    // -------------------------------------------------------------- speed --

    @Test
    fun `not measured on this PC yet until the PC has a real number`() {
        for (name in names("status_") - "status_after_one_answer") {
            val s = status(name)
            assertTrue(name, BigModel.nothingMeasured(s))
            assertEquals(
                name,
                listOf("Wiki builder: not measured on this PC yet.", "Deep questions: not measured on this PC yet."),
                BigModel.speedLines(s),
            )
        }
        val s = status("status_after_one_answer")
        assertFalse(BigModel.nothingMeasured(s))
        assertEquals(
            listOf(
                "Wiki builder: not measured on this PC yet.",
                "Deep questions: 1.12 words a second, 1.5 tokens a second. Last job took 8 s, on DeepSeek V4 Flash.",
            ),
            BigModel.speedLines(s),
        )
    }

    @Test
    fun `durations read as a person would say them`() {
        assertEquals("8 s", BigModel.duration(8.0))
        assertEquals("89 s", BigModel.duration(89.4))
        assertEquals("12 min 5 s", BigModel.duration(725.0))
        assertEquals("2 min", BigModel.duration(120.0))
        assertEquals("1 h 3 min", BigModel.duration(3780.0))
    }

    // -------------------------------------------------------------- reads --

    @Test
    fun `an older backend, a missing module and no network are each said plainly`() {
        val older = BigModel.readOf(ApiResult.Failed(ApiError.NotFound))
        assertEquals(BigModel.Read.OlderBackend, older)
        assertTrue(BigModel.readLine(older)!!.contains("apply-patches.ps1"))
        val missing = BigModel.readOf(ApiResult.Failed(ApiError.NotAvailable))
        assertEquals(BigModel.Read.NotInstalled, missing)
        assertTrue(BigModel.readLine(missing)!!.contains("jarvis_big_model.py"))
        val net = BigModel.deepReadOf(ApiResult.Failed(ApiError.Unreachable("timeout", "read_timeout")))
        // The plain words both apps use (PlainErrors), never the raw "timeout".
        assertEquals(PlainErrors.shown("timeout").text, BigModel.readLine(net))
        // A 200 that is not the shape is a failed read, never "nothing found".
        val odd = JarvisJson.parseToJsonElement("{\"ok\":true}") as JsonObject
        assertTrue(BigModel.readOf(ApiResult.Ok(odd)) is BigModel.Read.Failed)
        assertTrue(BigModel.deepReadOf(ApiResult.Ok(odd)) is BigModel.Read.Failed)
        val ok = BigModel.readOf(ApiResult.Ok(cases["status_ready_off"]!!.jsonObject))
        assertTrue(ok is BigModel.Read.Loaded<*>)
        assertNull(BigModel.readLine(ok))
    }

    // ------------------------------------------------------------- writes --

    @Test
    fun `the POST body is exactly switch and enabled`() {
        val body = JarvisJson.parseToJsonElement(BigModel.postBody(BigModel.DEEP, true)).jsonObject
        assertEquals(setOf("switch", "enabled"), body.keys)
        assertEquals("deep_questions", body["switch"]!!.jsonPrimitive.content)
        assertTrue(body["enabled"]!!.jsonPrimitive.boolean)
    }

    @Test
    fun `every real switch answer is read the way the plate needs`() {
        for (name in names("post_")) {
            val result = BigModel.classifyPost(code(name), body(name))
            assertTrue("$name: an answer, not a transport failure", result is ApiResult.Ok)
            val line = BigModel.replyLine(result)
            val error = body(name)["error"]?.jsonPrimitive?.content
            if (error != null) {
                // Shown word for word (docs/JARVIS-API.md section 14).
                assertEquals(name, error, line)
            } else {
                // A card is up, or it is off: the plate, re-read, says which.
                assertNull(name, line)
            }
        }
        assertEquals(409, code("post_master_on_again_409"))
        assertTrue(body("post_master_on_pending")["pending"]!!.jsonPrimitive.boolean)
        // "pending" never means on.
        assertFalse(body("post_master_on_pending")["enabled"]!!.jsonPrimitive.boolean)
    }

    @Test
    fun `an older backend, a missing module and a bad token on POST`() {
        val older = BigModel.classifyPost(404, null)
        assertEquals(ApiResult.Failed(ApiError.NotFound), older)
        assertTrue(BigModel.replyLine(older)!!.contains("apply-patches.ps1"))
        val missing = BigModel.classifyPost(
            503,
            JarvisJson.parseToJsonElement("{\"available\":false,\"error\":\"ImportError: x\"}").jsonObject,
        )
        assertEquals(ApiResult.Failed(ApiError.NotAvailable), missing)
        assertTrue(BigModel.replyLine(missing)!!.contains("jarvis_big_model.py"))
        assertEquals(ApiResult.Failed(ApiError.BadToken), BigModel.classifyPost(401, null))
        val down = BigModel.replyLine(ApiResult.Failed(ApiError.Unreachable("no route")))!!
        assertTrue(down, down.startsWith("Nothing changed. "))
        assertTrue(down, !down.contains("no route"))
    }

    // ----------------------------------------------------- deep questions --

    @Test
    fun `every deep case is read`() {
        for (name in names("deep_")) {
            val d = deep(name)
            assertTrue(name, d.why.isNotBlank())
            assertEquals(name, 4000, d.questionChars)
            assertEquals(name, 3, d.queue)
            d.jobs.forEach {
                assertTrue("$name ${it.id}", it.question.isNotBlank())
                assertTrue("$name ${it.id}", it.why.isNotBlank())
                assertEquals("$name ${it.id}: an answer only when done", it.state == "done", it.answer != null)
                assertFalse("$name ${it.id}", BigModel.stateLabel(it.state) == it.state)
            }
        }
    }

    @Test
    fun `off - not available, and the PC's reason instead of the box`() {
        val d = deep("deep_off")
        assertFalse(d.available)
        assertFalse(d.enabled)
        assertEquals("The big-model switch is off.", d.why)
        assertTrue(d.jobs.isEmpty())
        assertFalse(d.anyRunning)
    }

    @Test
    fun `a question still going - polled, no answer, no speed yet`() {
        for ((name, state) in listOf(
            "deep_queued" to "Waiting its turn",
            "deep_loading" to "Starting the big model",
            "deep_thinking" to "Thinking",
        )) {
            val d = deep(name)
            assertTrue(name, d.available)
            assertTrue("$name: polled while it runs", d.anyRunning)
            assertFalse(name, d.queueFull)
            val j = d.jobs.single()
            assertEquals(name, state, BigModel.stateLabel(j.state))
            assertNull(name, j.answer)
            assertNull(name, BigModel.jobMeta(j))
        }
    }

    @Test
    fun `done and failed - the answer as plain text, the time and the speed`() {
        val done = deep("deep_done")
        assertFalse(done.anyRunning)
        val j = done.jobs.single()
        assertEquals("Answered", BigModel.stateLabel(j.state))
        assertEquals("Because the sky scatters blue light more than red.", j.answer)
        assertEquals(listOf("Because the sky scatters blue light more than red."), BigModel.paragraphs(j.answer!!))
        assertEquals("Took 8 s, 1.12 words a second.", BigModel.jobMeta(j))
        assertTrue(j.why.startsWith("Answered in 8 s by DeepSeek V4 Flash"))

        val failed = deep("deep_failed")
        assertEquals(listOf("failed", "done"), failed.jobs.map { it.state })
        val f = failed.jobs.first()
        assertEquals("Not answered", BigModel.stateLabel(f.state))
        assertEquals("Not answered: the big model answered HTTP 500.", f.why)
        assertNull(f.answer)
        assertNull(BigModel.jobMeta(f))
    }

    @Test
    fun `an answer is split into paragraphs the way chat splits a reply`() {
        assertEquals(listOf("One.", "Two\nstill two.", "Three."), BigModel.paragraphs("One.\n\nTwo\nstill two.\n \nThree.\n"))
    }

    // --------------------------------------------------------------- ask --

    @Test
    fun `every real ask answer is shown in the PC's own words`() {
        for (name in names("ask_")) {
            // The shape JarvisApi.postForJob hands back as Ok, whatever the code.
            assertTrue(name, body(name).containsKey("state"))
            val asked = BigModel.askReply(ApiResult.Ok(body(name)))
            if (name == "ask_accepted") {
                assertEquals(202, code(name))
                assertTrue(asked.queued)
                assertEquals(body(name)["message"]!!.jsonPrimitive.content, asked.text)
            } else {
                assertFalse(name, asked.queued)
                assertEquals(name, body(name)["error"]!!.jsonPrimitive.content, asked.text)
            }
        }
        assertEquals(503, code("ask_refused_off"))
        assertEquals(400, code("ask_empty_400"))
    }

    @Test
    fun `the phone refuses an empty or too-long question before sending it`() {
        assertEquals("Type a question first.", BigModel.askProblem("   ", 4000))
        assertEquals(
            "The question is 4,001 characters; at most 4,000.",
            BigModel.askProblem("x".repeat(4001), 4000),
        )
        assertNull(BigModel.askProblem("  Why is the sky blue?  ", 4000))
        assertNull(BigModel.askBody("  "))
        val body = JarvisJson.parseToJsonElement(BigModel.askBody("  Why \"blue\"?\n ")!!).jsonObject
        assertEquals(setOf("question"), body.keys)
        assertEquals("Why \"blue\"?", body["question"]!!.jsonPrimitive.content)
    }

    @Test
    fun `a failed ask says nothing was asked`() {
        val down = BigModel.askReply(ApiResult.Failed(ApiError.Unreachable("no route")))
        assertFalse(down.queued)
        assertTrue(down.text, down.text.startsWith("Not asked. "))
        assertTrue(down.text, !down.text.contains("no route"))
        assertTrue(BigModel.askReply(ApiResult.Failed(ApiError.NotFound)).text.contains("apply-patches.ps1"))
    }
}
