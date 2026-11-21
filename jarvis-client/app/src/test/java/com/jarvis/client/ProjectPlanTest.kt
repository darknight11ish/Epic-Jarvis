package com.jarvis.client

import com.jarvis.client.net.ApiResult
import com.jarvis.client.net.JarvisApi
import com.jarvis.client.net.ProjectPlan
import com.jarvis.client.net.Projects
import kotlinx.coroutines.runBlocking
import kotlinx.serialization.json.Json
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.int
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
 * PM4, the phone half (2026-11-21): the concise Projects screen - the Next 3
 * ready tasks, a tap that marks one Done through the PC's EXISTING status path,
 * and a Quick Add that sends the owner's typed words and nothing else.
 *
 * The answers are the real PC's: `contract/projects-cases.json` is written by
 * `tools/gen_projects_cases.py` from a real run of `jarvis_projects.py`, and
 * the two writes here go through the real client ([JarvisApi] with
 * MockWebServer as the fake transport) so the route, the method and the body
 * are pinned, not only a helper's return value. The rules this file keeps:
 *
 *  - the ready list is at most [ProjectPlan.READY_CAP] (3) and names its project;
 *  - a tap is ONE change on the ONE existing route, with the store's own
 *    receipt/Undo, never a second invented call;
 *  - Quick Add carries exactly the words typed - no date, no status, no class;
 *  - an empty plan, an unreadable one and a PC without the route all say so,
 *    and no row is invented for any of them;
 *  - the spoken answer over the same data is capped at the same 3.
 *
 * The Compose screen itself is pinned by a source test at the end: Compose
 * cannot run on a plain JVM, so that test reads `ProjectsPlate.kt` and proves it
 * calls these builders and no other write path.
 */
class ProjectPlanTest {

    private val json = Json { ignoreUnknownKeys = true }

    private val doc: JsonObject = run {
        val text = requireNotNull(javaClass.classLoader?.getResource("contract/projects-cases.json")) {
            "contract/projects-cases.json is missing - run tools/gen_projects_cases.py"
        }.readText()
        json.parseToJsonElement(text) as JsonObject
    }
    private val cases = doc["cases"]!!.jsonObject
    private val posts = doc["posts"]!!.jsonObject

    private val pid = "0".repeat(31) + "a"

    private fun planCase(name: String): JsonObject = cases[name]!!.jsonObject

    private fun parsed(name: String, projectName: String = "Kitchen"): ProjectPlan.Plan =
        ProjectPlan.parse(pid, projectName, planCase(name))!!

    private fun bodyOf(post: String): JsonObject = posts[post]!!.jsonObject["body"]!!.jsonObject
    private fun codeOf(post: String): Int = posts[post]!!.jsonObject["status"]!!.jsonPrimitive.int
    private fun reply(post: String) = Projects.Reply(codeOf(post), bodyOf(post))

    // ------------------------------------------------- the contract's words ---

    @Test
    fun `the words and the cap are the contract's, word for word`() {
        val words = doc["plan_words"]!!.jsonObject
        assertEquals(words.keys, ProjectPlan.WORDS.keys)
        for ((k, v) in words) assertEquals(k, v.jsonPrimitive.content, ProjectPlan.WORDS[k])
        val limits = doc["plan_limits"]!!.jsonObject
        assertEquals(limits["ready_cap"]!!.jsonPrimitive.int, ProjectPlan.READY_CAP)
        assertEquals("the phone's screen shows 3", 3, ProjectPlan.READY_CAP)
        // The PC's own read is bounded, and the contract says where.
        assertTrue(limits["listed_ready_max"]!!.jsonPrimitive.int > ProjectPlan.READY_CAP)
        assertTrue(limits["events_max"]!!.jsonPrimitive.int > 0)
        assertEquals(120, limits["work_title"]!!.jsonPrimitive.int)
    }

    // ------------------------------------------------------ the plan read ----

    @Test
    fun `the plan read is the real answer, and nothing in it is invented`() {
        val p = parsed("plan_full")
        assertEquals("Kitchen", p.projectName)
        assertEquals(pid, p.projectId)
        assertEquals("Repaint the kitchen before winter", p.objective)
        assertEquals("Walls done and the shelves back up", p.successCriteria)
        assertEquals("active", p.status)
        assertEquals("2026-12-01", p.targetDate)
        assertEquals("owner/kitchen", p.linkedRepo)
        assertEquals("Notes/Kitchen.md", p.linkedNotePath)
        assertNull("no slug was set, so there is none", p.slug)
        assertEquals(2, p.counts.milestones)
        assertEquals(4, p.counts.workItems)
        assertEquals(2, p.counts.ready)
        assertEquals(1, p.counts.blocked)
        assertEquals(1, p.counts.edges)
        assertEquals(8, p.counts.events)
        assertEquals(listOf("Prepare", "Paint"), p.milestones.map { it.title })
        assertEquals(1, p.milestones[0].done)
        assertEquals(1, p.milestones[0].workItems)
        assertEquals(0, p.milestones[1].done)
        assertEquals(3, p.milestones[1].workItems)
        assertEquals(
            listOf("Buy paint", "Tape the edges", "Paint the walls", "Clear the counters"),
            p.items.map { it.title },
        )
        val byTitle = p.items.associateBy { it.title }
        val buy = byTitle.getValue("Buy paint")
        val tape = byTitle.getValue("Tape the edges")
        val walls = byTitle.getValue("Paint the walls")
        assertEquals("2026-11-25", buy.dueDate)
        assertNull("undated on the PC stays undated here", tape.dueDate)
        assertEquals(0, buy.priority)
        assertNull("no priority set reads as none", walls.priority)
        assertTrue(buy.ready)
        assertTrue(tape.ready)
        assertFalse("a blocked item is never ready", walls.ready)
        assertEquals(listOf(tape.id), walls.blockedByIds)
        assertEquals("owner", buy.executor)
        // The store's own ready order, as the PC sent it.
        assertEquals(listOf(buy.id, tape.id), p.ready)
        assertEquals(listOf("Buy paint", "Tape the edges"),
            ProjectPlan.readyTasks(listOf(p)).map { it.title })
        // Events are newest first, and the read never adds one.
        assertTrue(p.events.isNotEmpty())
        assertEquals("work_item_added", p.events.first().kind)
        assertEquals("project_plan_changed", p.events.last().kind)
        assertEquals(8, p.events.size)
    }

    @Test
    fun `an empty plan says it is empty and invents no row`() {
        val p = parsed("plan_empty", "Empty")
        assertNull(p.objective)
        assertNull(p.successCriteria)
        assertNull(p.status)
        assertNull(p.targetDate)
        assertTrue(p.milestones.isEmpty())
        assertTrue(p.items.isEmpty())
        assertTrue(p.ready.isEmpty())
        assertTrue(p.events.isEmpty())
        assertEquals(0, p.counts.workItems)
        assertEquals(0, p.counts.ready)
        assertTrue(ProjectPlan.readyTasks(listOf(p)).isEmpty())
        assertEquals(ProjectPlan.w("speech_none"), ProjectPlan.spoken(emptyList(), 0))
    }

    @Test
    fun `a body that is not a plan is not read as one`() {
        assertNull(ProjectPlan.parse(pid, "Kitchen", null))
        assertNull(ProjectPlan.parse(pid, "Kitchen", JsonObject(emptyMap())))
        assertNull("the PC's own refusal is not a plan", ProjectPlan.parse(
            pid, "Kitchen",
            JsonObject(mapOf("ok" to JsonPrimitive(false), "error" to JsonPrimitive("No such project."))),
        ))
        // A PC without the route (an older install): 404 with no `ok:false` is
        // "not there yet", so the screen says run apply-patches and no row appears.
        val olderPc = Projects.Reply(404, JsonObject(emptyMap()))
        assertTrue(Projects.isMissing(olderPc))
        assertNull(ProjectPlan.parse(pid, "Kitchen", olderPc.body))
        // A PC's own 404 (its `ok:false`) is a sentence, not "not installed".
        val own404 = Projects.Reply(404, JsonObject(mapOf(
            "ok" to JsonPrimitive(false), "error" to JsonPrimitive("No such project."),
        )))
        assertFalse(Projects.isMissing(own404))
        assertEquals("No such project.", ProjectPlan.readError(own404))
        assertEquals("Your PC could not answer that read. Nothing was changed.", ProjectPlan.readError(Projects.Reply(500, null)))
    }

    // ------------------------------------------------ the 3-item rule --------

    private data class Spec(
        val id: String,
        val title: String,
        val priority: Int? = null,
        val due: String? = null,
        val created: Double = 0.0,
    )

    /** One plan read, built to the frozen shape, for the merge/order/cap tests. */
    private fun planOf(
        projectId: String,
        projectName: String,
        specs: List<Spec>,
        ready: List<String> = specs.map { it.id },
        totalReady: Int = specs.size,
    ): ProjectPlan.Plan {
        val items = specs.joinToString(",") { s ->
            val priority = s.priority?.toString() ?: "null"
            val due = s.due?.let { JsonPrimitive(it).toString() } ?: "null"
            """{"id":"${s.id}","project":"$projectId","project_name":${JsonPrimitive(projectName)},""" +
                """"milestone":null,"title":${JsonPrimitive(s.title)},"detail":"",""" +
                """"status":"ready","priority":$priority,"due_date":$due,"created":${s.created},""" +
                """"changed":0.0,"blocked_by":[],"ready":true,"executor":"owner",""" +
                """"linked_task_id":null,"linked_pr_number":null,"linked_pr_state":"",""" +
                """"linked_ci_status":""}"""
        }
        val readyJson = ready.joinToString(",") { JsonPrimitive(it).toString() }
        val text = """{"ok":true,"available":true,"objective":null,"success_criteria":null,""" +
            """"status":null,"target_date":null,"linked_repo":null,"linked_note_path":null,""" +
            """"slug":null,"counts":{"milestones":0,"work_items":${specs.size},""" +
            """"ready":$totalReady,"blocked":0,"edges":0,"events":0},"milestones":[],""" +
            """"work_items":[$items],"ready":[$readyJson],"events":[]}"""
        return ProjectPlan.parse(projectId, projectName,
            json.parseToJsonElement(text) as JsonObject)!!
    }

    @Test
    fun `the ready list is at most 3 and every row names its project`() {
        val five = planOf("1".repeat(32), "Kitchen", (1..5).map {
            Spec(it.toString().repeat(31) + "a", "Task $it", priority = it, created = it.toDouble())
        })
        val tasks = ProjectPlan.readyTasks(listOf(five))
        assertEquals("the cap is a rule, not a layout choice", 3, tasks.size)
        assertEquals(listOf("Task 1", "Task 2", "Task 3"), tasks.map { it.title })
        for (t in tasks) assertEquals("Kitchen", t.projectName)
        assertEquals(5, ProjectPlan.totalReady(listOf(five)))
        // Two plans: the store's own order is merged, not "project by project".
        val a = planOf("2".repeat(32), "Kitchen", listOf(
            Spec("a".repeat(32), "Later", priority = 2, created = 1.0),
            Spec("b".repeat(32), "No priority", priority = null, created = 2.0),
        ))
        val b = planOf("3".repeat(32), "Garden", listOf(
            Spec("c".repeat(32), "First", priority = 0, created = 3.0),
            Spec("d".repeat(32), "Second", priority = 1, created = 4.0),
        ))
        val merged = ProjectPlan.readyTasks(listOf(a, b))
        assertEquals(listOf("First", "Second", "Later"), merged.map { it.title })
        assertEquals(listOf("Garden", "Garden", "Kitchen"), merged.map { it.projectName })
        // A blocked item the PC did not list as ready is never shown, however
        // old the other read is.
        val stale = planOf("4".repeat(32), "Kitchen", listOf(Spec("e".repeat(32), "Ready")))
        assertTrue(ProjectPlan.readyTasks(listOf(stale.copy(ready = emptyList()))).isEmpty())
        // The due date is the store's second key, and it is never invented.
        val dated = planOf("6".repeat(32), "Kitchen", listOf(
            Spec("f".repeat(32), "Undated", due = null, created = 1.0),
            Spec("1".repeat(32), "Due later", due = "2026-12-02", created = 2.0),
            Spec("2".repeat(32), "Due sooner", due = "2026-11-30", created = 3.0),
        ))
        assertEquals(listOf("Due sooner", "Due later", "Undated"),
            ProjectPlan.readyTasks(listOf(dated)).map { it.title })
    }

    @Test
    fun `the voice answer over the same data is capped at 3 items`() {
        val p = planOf("5".repeat(32), "Kitchen", (1..5).map {
            Spec(it.toString().repeat(31) + "a", "Task $it", priority = it)
        })
        val tasks = ProjectPlan.readyTasks(listOf(p))
        val said = ProjectPlan.spoken(tasks, 7)
        assertTrue(said, said.startsWith(
            "Ready now: Task 1 in Kitchen, Task 2 in Kitchen, Task 3 in Kitchen.",
        ))
        assertFalse("the fourth item is never said", said.contains("Task 4"))
        assertFalse("nor the fifth", said.contains("Task 5"))
        assertTrue("and it says how many more there are: $said", said.contains("4 more"))
        // However many are handed in, the spoken answer stays 3.
        val many = planOf("7".repeat(32), "Kitchen", (1..8).map {
            Spec(it.toString().repeat(31) + "b", "Item $it", priority = it)
        })
        val spoken = ProjectPlan.spoken(ProjectPlan.readyTasks(listOf(many)), 8)
        assertEquals(3, spoken.split(" in Kitchen").size - 1)
        assertEquals(ProjectPlan.w("speech_none"), ProjectPlan.spoken(emptyList(), 0))
    }

    // --------------------------------------------------- one route, one tap --

    private lateinit var server: MockWebServer
    private lateinit var settings: FakeHost
    private lateinit var tokens: FakeTokens
    private lateinit var api: JarvisApi
    private val routes = mutableMapOf<String, MockResponse>()

    private fun ok(body: JsonObject) = MockResponse().setResponseCode(200)
        .setHeader("Content-Type", "application/json").setBody(body.toString())

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

    @Test
    fun `a tap marks done through the one existing route and nothing else`() = runBlocking {
        val p = parsed("plan_full")
        val item = p.items.first { it.title == "Buy paint" }
        val req = ProjectPlan.doneRequest(p.projectId, item.id)!!
        routes[req.path] = ok(bodyOf("work_item_status"))
        val result = api.projectsCall(req.path, req.body)
        assertTrue("the PC answered: $result", result is ApiResult.Ok)
        assertEquals("ONE request for ONE tap", 1, server.requestCount)
        val sent = server.takeRequest()
        assertEquals("POST", sent.method)
        assertEquals("/api/projects/${p.projectId}/work_items/${item.id}/status", sent.path)
        assertEquals("""{"status":"done"}""", sent.body.readUtf8())
        // The PC's own answer reads as a done change with its own sentence.
        val outcome = Projects.said((result as ApiResult.Ok).value, ProjectPlan.w("done_said"))
        assertTrue(outcome.changed)
        assertFalse(outcome.waiting)
        assertTrue(outcome.said, outcome.said.contains("Buy paint"))
        // The one route is built only by ProjectPlan; the old action list has no
        // invented entry for a status change.
        assertNull("no invented write action",
            Projects.writePath("work_item_status", p.projectId))
        assertNull("no invented done action", Projects.writePath("done", p.projectId))
        assertNull("a bad id builds no path", ProjectPlan.statusPath(p.projectId, "not-an-id"))
        assertEquals(
            "/api/projects/${p.projectId}/work_items/${item.id}/status",
            ProjectPlan.statusPath(p.projectId, item.id),
        )
        // The PC's refusal keeps its own words (an unknown item, the real answer).
        val refused = Projects.said(reply("work_item_status_unknown"), ProjectPlan.w("done_said"))
        assertFalse(refused.changed)
        assertTrue(refused.said, refused.said.contains("no work item with that id", ignoreCase = true))
        // "Already done" is an answer, not a second write.
        assertEquals(200, codeOf("work_item_status_again"))
        val again = Projects.said(reply("work_item_status_again"), ProjectPlan.w("done_said"))
        assertFalse(again.waiting)
        assertTrue(again.said.isNotBlank())
        assertTrue("the second answer says the new state: ${again.said}",
            again.said.contains("done"))
    }

    @Test
    fun `Quick Add sends exactly the typed words`() = runBlocking {
        val p = parsed("plan_full")
        val req = ProjectPlan.addRequest(p.projectId, "  Buy a brush  ")!!
        assertEquals("/api/projects/${p.projectId}/work_items", req.path)
        assertEquals("""{"title":"Buy a brush"}""", req.body)
        for (invented in listOf("due_date", "status", "priority", "milestone", "executor")) {
            assertFalse("Quick Add never sends $invented", req.body.contains(invented))
        }
        assertNull("no words, no request", ProjectPlan.addRequest(p.projectId, "   "))
        assertNull("no project, no request", ProjectPlan.addRequest("nope", "Buy a brush"))
        routes[req.path] = ok(bodyOf("quick_add"))
        val result = api.projectsCall(req.path, req.body)
        assertTrue("the PC answered: $result", result is ApiResult.Ok)
        assertEquals(1, server.requestCount)
        val sent = server.takeRequest()
        assertEquals("POST", sent.method)
        assertEquals("/api/projects/${p.projectId}/work_items", sent.path)
        assertEquals("""{"title":"Buy a brush"}""", sent.body.readUtf8())
        val outcome = Projects.said((result as ApiResult.Ok).value, ProjectPlan.w("quick_said"))
        assertTrue(outcome.changed)
        assertTrue(outcome.said, outcome.said.contains("Buy a brush"))
        val blank = Projects.said(reply("quick_add_blank"), ProjectPlan.w("quick_said"))
        assertFalse(blank.changed)
        assertTrue(blank.said.isNotBlank())
        // This door takes the owner's words only - a date in the body is refused
        // by the PC (the anti-hallucination rule), so a typed task never dates itself.
        assertEquals(400, codeOf("quick_add_date"))
        val dated = Projects.said(reply("quick_add_date"), ProjectPlan.w("quick_said"))
        assertFalse(dated.changed)
        assertTrue(dated.said, dated.said.contains("date is never", ignoreCase = true))
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
    fun `the screen draws these builders, and the only writes are the two tested`() {
        val root = repoRoot()
        val plate = java.io.File(root,
            "jarvis-client/app/src/main/java/com/jarvis/client/ui/screens/ProjectsPlate.kt",
        ).readText()
        assertTrue("each project's plan is one read", plate.contains("ProjectPlan.planPath"))
        assertTrue("the ready list comes from the plan read", plate.contains("ProjectPlan.readyTasks"))
        assertTrue("the spoken summary is the same data, capped", plate.contains("ProjectPlan.spoken"))
        assertTrue("the tap is the tested builder", plate.contains("ProjectPlan.doneRequest"))
        assertTrue("Quick Add is the tested builder", plate.contains("ProjectPlan.addRequest"))
        assertTrue("a tap posts the one existing status change",
            plate.contains("change(\"work_item_status\""))
        assertTrue("Quick Add posts one work item",
            plate.contains("change(\"work_item_add\""))
        assertTrue("nothing is sent while the words are blank",
            plate.contains("quickWords.isNotBlank()"))
        // The work-item routes live in exactly ONE phone source file: no screen
        // invents a second call beside the tested builder.
        val main = java.io.File(root, "jarvis-client/app/src/main/java")
        val writers = main.walkTopDown()
            .filter { it.isFile && it.name.endsWith(".kt") }
            .filter { it.readText().contains("/work_items") }
            .map { it.name }
            .sorted()
            .toList()
        assertEquals(listOf("ProjectPlan.kt"), writers)
    }

    private companion object {
        const val TOKEN = "jarvis_pair_contract_test"
    }
}
