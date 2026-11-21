package com.jarvis.client

import com.jarvis.client.net.ApiResult
import com.jarvis.client.net.JarvisApi
import com.jarvis.client.net.ProjectPlan
import com.jarvis.client.net.Projects
import kotlinx.coroutines.runBlocking
import kotlinx.serialization.json.Json
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.jsonObject
import kotlinx.serialization.json.jsonPrimitive
import okhttp3.mockwebserver.Dispatcher
import okhttp3.mockwebserver.MockResponse
import okhttp3.mockwebserver.MockWebServer
import okhttp3.mockwebserver.RecordedRequest
import org.junit.After
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Before
import org.junit.Test

/**
 * Ruling 5.7 (the external review's rulings, 2026-11-21): a Done tap on a work
 * item whose plan read still shows a linked PR open, or a linked durable job
 * still running/waiting, shows ONE confirmation first - the PR number and/or the
 * job named - instead of silently marking the item done or hard-blocking it.
 * "Mark done anyway" then sends exactly the ONE status request the immediate tap
 * would have sent (the same existing route, the same body, one receipt);
 * "Cancel" sends nothing and changes nothing. No link, or a link whose state the
 * PC has not read (a merged or closed PR, a job the store's own projection
 * already settled), taps through immediately - a missing link state never warns.
 *
 * The decisions and the words are the real code's ([ProjectPlan.doneWarning],
 * [ProjectPlan.doneStep]) over an item shaped exactly as
 * `GET /api/projects/<id>/plan` returns it (JARVIS-API section 88.10, and the
 * `plan_full` answer `tools/gen_projects_cases.py` writes). The confirming POST
 * goes through the real client ([JarvisApi] with MockWebServer as the fake
 * transport), so the route, the method, the body and the count are pinned - not
 * only a helper's return value. Compose cannot run on a plain JVM, so the last
 * test reads `ProjectsPlate.kt` and proves the screen asks through these
 * builders and writes only through the one [ProjectPlan.doneRequest] it carries.
 *
 * These tests are RED on the tree before this change (c96e1c52a): the tree has
 * no warning at all, so `doneWarning`/`doneStep`/the `done_warning_*` words do
 * not exist there and neither does the confirmation in `ProjectsPlate.kt`.
 */
class ProjectDoneWarningTest {

    private val json = Json { ignoreUnknownKeys = true }

    private val doc: JsonObject = run {
        val text = requireNotNull(javaClass.classLoader?.getResource("contract/projects-cases.json")) {
            "contract/projects-cases.json is missing - run tools/gen_projects_cases.py"
        }.readText()
        json.parseToJsonElement(text) as JsonObject
    }
    private val posts = doc["posts"]!!.jsonObject

    private val pid = "0".repeat(31) + "a"
    private val wid = "1".repeat(31) + "b"
    private val taskId = "a".repeat(32)

    // ------------------------------------------------------- the plan read ----

    /** One work item, exactly as the plan read shapes it, with the links a test needs. */
    private fun workItemJson(
        pr: Int? = null,
        prState: String = "",
        ci: String = "",
        task: String? = null,
        status: String = "ready",
        title: String = "Buy paint",
    ): String {
        val taskJson = task?.let { JsonPrimitive(it).toString() } ?: "null"
        return """{"id":"$wid","project":"$pid","project_name":"Kitchen",""" +
            """"milestone":null,"title":${JsonPrimitive(title)},"detail":"","status":"$status",""" +
            """"priority":0,"due_date":null,"created":1.0,"changed":2.0,"blocked_by":[],""" +
            """"ready":true,"executor":"owner","linked_task_id":$taskJson,""" +
            """"linked_pr_number":${pr ?: "null"},"linked_pr_state":${JsonPrimitive(prState)},""" +
            """"linked_ci_status":${JsonPrimitive(ci)}}"""
    }

    /** A plan whose one item is the linked/status shape given, and is listed ready. */
    private fun answer(
        pr: Int? = null,
        prState: String = "",
        ci: String = "",
        task: String? = null,
        status: String = "ready",
    ): ProjectPlan.Plan {
        val text = """{"ok":true,"available":true,"objective":null,"success_criteria":null,""" +
            """"status":null,"target_date":null,"linked_repo":null,"linked_note_path":null,""" +
            """"slug":null,"counts":{"milestones":0,"work_items":1,"ready":1,"blocked":0,""" +
            """"edges":0,"events":0},"milestones":[],""" +
            """"work_items":[${workItemJson(pr, prState, ci, task, status)}],""" +
            """"ready":["$wid"],"events":[]}"""
        return ProjectPlan.parse(pid, "Kitchen", json.parseToJsonElement(text) as JsonObject)!!
    }

    // ------------------------------------------------- the tap asks first -----

    @Test
    fun `an open linked PR asks first, names the number, and sends nothing yet`() {
        val plan = answer(pr = 42, prState = "open", ci = "failed")
        val item = plan.items.single()
        val step = ProjectPlan.doneStep(pid, item)
        assertTrue("an open PR must ASK, not send: $step", step is ProjectPlan.DoneStep.Ask)
        val ask = step as ProjectPlan.DoneStep.Ask
        assertEquals(
            "Linked PR #42 is still open - mark done anyway?",
            ask.warning.message,
        )
        assertEquals("Mark done anyway", ask.warning.confirm)
        assertEquals("Cancel", ask.warning.cancel)
        // Nothing has been posted: the one request is HELD in the warning, and
        // it is exactly the request the immediate tap builds - not a second one.
        assertEquals("nothing is sent before the owner taps Mark done anyway", 0, server.requestCount)
        assertEquals(ProjectPlan.doneRequest(pid, item.id)!!, ask.request)
        assertEquals("/api/projects/$pid/work_items/${item.id}/status", ask.request.path)
        assertEquals("""{"status":"done"}""", ask.request.body)
    }

    @Test
    fun `confirming sends exactly one POST on the one existing status route`() = runBlocking {
        val plan = answer(pr = 42, prState = "open")
        val item = plan.items.single()
        val ask = ProjectPlan.doneStep(pid, item) as ProjectPlan.DoneStep.Ask
        routes[ask.request.path] = ok(bodyOf("work_item_status"))
        // Mark done anyway: the one tap the dialog offers sends the held request.
        val result = api.projectsCall(ask.request.path, ask.request.body)
        assertTrue("the PC answered: $result", result is ApiResult.Ok)
        assertEquals("one confirmation is ONE status change", 1, server.requestCount)
        val sent = server.takeRequest()
        assertEquals("POST", sent.method)
        assertEquals("/api/projects/$pid/work_items/${item.id}/status", sent.path)
        assertEquals("""{"status":"done"}""", sent.body.readUtf8())
        // The same ONE route the immediate tap uses - no second invented door.
        assertNull(Projects.writePath("work_item_status", pid))
        assertNull(Projects.writePath("done", pid))
        assertEquals(ProjectPlan.doneRequest(pid, item.id), ask.request)
        val outcome = Projects.said(
            (result as ApiResult.Ok).value, ProjectPlan.w("done_said"),
        )
        assertTrue("the PC's own change sentence still comes back", outcome.changed)
    }

    @Test
    fun `cancelling sends nothing and the row is unchanged`() {
        val plan = answer(pr = 42, prState = "open")
        val item = plan.items.single()
        val ask = ProjectPlan.doneStep(pid, item) as ProjectPlan.DoneStep.Ask
        // Cancel is the dialog's dismiss button: it only puts the dialog away.
        assertEquals("Cancel", ask.warning.cancel)
        assertEquals("nothing was sent", 0, server.requestCount)
        // The row the screen already read is untouched: same item, same status,
        // still on the PC's own ready list - the read is what the PC answered.
        assertEquals(item, plan.item(item.id))
        assertEquals("ready", plan.item(item.id)!!.status)
        assertTrue(plan.ready.contains(item.id))
    }

    @Test
    fun `a settled or unlinked item taps through immediately`() {
        val direct = listOf(
            "a merged PR" to answer(pr = 42, prState = "merged", ci = "green"),
            "a closed PR" to answer(pr = 42, prState = "closed", ci = "failed"),
            "no link at all" to answer(),
            "a PR whose state was never read" to answer(pr = 42, prState = ""),
            "a job whose own state the projection already settled" to
                answer(task = taskId, status = "in_review"),
            "a job whose projection has not run yet" to answer(task = taskId, status = "ready"),
        )
        for ((why, plan) in direct) {
            val item = plan.items.single()
            assertNull("$why: a missing or settled link never warns", ProjectPlan.doneWarning(item))
            val step = ProjectPlan.doneStep(pid, item)
            assertTrue("$why must tap through immediately: $step", step is ProjectPlan.DoneStep.Send)
            val sent = (step as ProjectPlan.DoneStep.Send).request
            assertEquals("/api/projects/$pid/work_items/${item.id}/status", sent.path)
            assertEquals("""{"status":"done"}""", sent.body)
        }
        assertEquals("no tap-through sent anything by itself", 0, server.requestCount)
    }

    @Test
    fun `a running or waiting linked job gets its own confirmation word`() {
        val running = answer(task = taskId, status = "in_progress").items.single()
        val runningStep = ProjectPlan.doneStep(pid, running) as ProjectPlan.DoneStep.Ask
        assertEquals(
            "The linked job is still running - mark done anyway?",
            runningStep.warning.message,
        )

        val waiting = answer(task = taskId, status = "waiting_approval").items.single()
        val waitingStep = ProjectPlan.doneStep(pid, waiting) as ProjectPlan.DoneStep.Ask
        assertEquals(
            "The linked job is still waiting on you - mark done anyway?",
            waitingStep.warning.message,
        )

        // Both links live: the one message names both.
        val both = answer(pr = 42, prState = "open", task = taskId, status = "in_progress")
            .items.single()
        val bothStep = ProjectPlan.doneStep(pid, both) as ProjectPlan.DoneStep.Ask
        assertEquals(
            "Linked PR #42 is still open, and the linked job is still running - " +
                "mark done anyway?",
            bothStep.warning.message,
        )
        val bothWaiting = answer(pr = 7, prState = "open", task = taskId,
            status = "waiting_approval").items.single()
        val bothWaitingStep = ProjectPlan.doneStep(pid, bothWaiting) as ProjectPlan.DoneStep.Ask
        assertEquals(
            "Linked PR #7 is still open, and the linked job is still waiting on you - " +
                "mark done anyway?",
            bothWaitingStep.warning.message,
        )
        // The warning is words only: none of these taps has been sent.
        assertEquals(0, server.requestCount)
    }

    // ----------------------------------------- the contract's words, keyed ----

    @Test
    fun `the warning words are the contract's, word for word`() {
        val words = doc["plan_words"]!!.jsonObject
        for (key in listOf(
            "done_warning_pr", "done_warning_job", "done_warning_job_waiting",
            "done_warning_both", "done_warning_both_waiting", "done_warning_ask",
            "done_anyway", "done_cancel",
        )) {
            val entry = words[key]
            assertTrue("plan_words has no \"$key\" - run tools/gen_projects_cases.py",
                entry != null)
            assertEquals(key, entry!!.jsonPrimitive.content, ProjectPlan.WORDS[key])
        }
        // The ruling's own shape: the number in the warning, the question last.
        assertEquals(
            "Linked PR #42 is still open - mark done anyway?",
            ProjectPlan.fill(ProjectPlan.WORDS.getValue("done_warning_ask"), "why" to
                ProjectPlan.fill(ProjectPlan.WORDS.getValue("done_warning_pr"), "n" to 42)),
        )
    }

    // ------------------------------------- the screen the JVM cannot draw -----

    private fun repoRoot(): java.io.File {
        var dir: java.io.File? = java.io.File(System.getProperty("user.dir") ?: ".").absoluteFile
        while (dir != null) {
            if (java.io.File(dir, "jarvis-client/app/src/main").isDirectory) return dir
            dir = dir.parentFile
        }
        error("the repository root was not found above ${System.getProperty("user.dir")}")
    }

    @Test
    fun `the screen asks through the tested builders and writes only on confirm`() {
        val plate = java.io.File(
            repoRoot(),
            "jarvis-client/app/src/main/java/com/jarvis/client/ui/screens/ProjectsPlate.kt",
        ).readText()
        assertTrue("the tap reads the plan read's own linked state",
            plate.contains("ProjectPlan.doneStep"))
        assertTrue("the tap asks instead of sending when a link is live",
            plate.contains("ProjectPlan.DoneStep.Ask -> confirmDone"))
        assertTrue("the dialog shows the plan read's own warning",
            plate.contains("AlertDialog") && plate.contains("step.warning.message"))
        assertTrue("Mark done anyway sends the ONE held request",
            plate.contains("markDone(step.request)"))
        assertTrue("Cancel only puts the dialog away",
            plate.contains("step.warning.cancel") && plate.contains("confirmDone = null"))
        assertTrue("the one status change the screen makes is in markDone",
            plate.contains("fun markDone") && plate.contains("change(\"work_item_status\""))
        assertFalse("the screen never builds a second request on the confirm path",
            plate.contains("ProjectPlan.doneRequest"))
        // The work-item routes still live in exactly ONE phone source file.
        val main = java.io.File(repoRoot(), "jarvis-client/app/src/main/java")
        val writers = main.walkTopDown()
            .filter { it.isFile && it.name.endsWith(".kt") }
            .filter { it.readText().contains("/work_items") }
            .map { it.name }
            .sorted()
            .toList()
        assertEquals(listOf("ProjectPlan.kt"), writers)
    }

    // ------------------------------------------------------------ transport --

    private lateinit var server: MockWebServer
    private lateinit var settings: FakeHost
    private lateinit var tokens: FakeTokens
    private lateinit var api: JarvisApi
    private val routes = mutableMapOf<String, MockResponse>()

    private fun ok(body: JsonObject) = MockResponse().setResponseCode(200)
        .setHeader("Content-Type", "application/json").setBody(body.toString())

    private fun bodyOf(post: String): JsonObject = posts[post]!!.jsonObject["body"]!!.jsonObject

    @Before
    fun start() {
        server = MockWebServer()
        server.dispatcher = object : Dispatcher() {
            override fun dispatch(request: RecordedRequest): MockResponse {
                val path = request.path?.substringBefore('?').orEmpty()
                return routes[path] ?: MockResponse().setResponseCode(404).setBody("{}")
            }
        }
        server.start()
        settings = FakeHost()
        settings.setHost("127.0.0.1:${server.port}")
        tokens = FakeTokens()
        tokens.setToken(TOKEN)
        api = JarvisApi(settings, tokens)
    }

    @After
    fun stop() {
        tokens.clear()
        settings.setHost("")
        server.shutdown()
    }

    private companion object {
        const val TOKEN = "jarvis_pair_contract_test"
    }
}
