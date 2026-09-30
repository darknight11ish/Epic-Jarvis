package com.jarvis.client

import com.jarvis.client.net.ApiError
import com.jarvis.client.net.Goals
import com.jarvis.client.net.JarvisJson
import com.jarvis.client.net.Projects
import com.jarvis.client.net.Schedule
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.boolean
import kotlinx.serialization.json.int
import kotlinx.serialization.json.jsonArray
import kotlinx.serialization.json.jsonObject
import kotlinx.serialization.json.jsonPrimitive
import kotlinx.serialization.json.JsonNull
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNotNull
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test
import java.io.File

/**
 * "Goals" on the phone (the owner's "build it now", 2026-09-27;
 * docs/JARVIS-API.md section 59; [Goals]). The shapes read here are the
 * ones `backend/jarvis_goals.py` sends (`backend/test_goals.py` runs the
 * PC side of the same contract).
 */
class GoalsTest {

    private fun obj(json: String) = JarvisJson.parseToJsonElement(json) as JsonObject

    private val listAnswer = obj(
        """{"ok":true,"goals":[
            {"id":"g0000000001","text":"insulate the garage before winter",
             "plan":[{"step":"contact 3 installers","by":"this week","done":false},
                     {"step":"pick one and book it","by":"","done":false}],
             "status":"active","created":1790000000.0,"changed":1790000100.0},
            {"id":"g0000000002","text":"a stopped one","plan":[{"step":"x","by":"","done":false}],
             "status":"stopped","created":1789999000.0,"changed":1789999100.0},
            {"id":"not-a-real-id","text":"dropped","plan":[],"status":"draft","created":1,"changed":1},
            {"id":"g0000000003","text":"no plan at all","status":"draft","created":1,"changed":1}
        ],"limits":{"text":300,"steps":7,"goals":20,"by":40}}""",
    )

    @Test
    fun theListIsReadAndARowWithoutAValidIdOrAPlanIsDropped() {
        val v = Goals.parse(listAnswer)!!
        assertEquals(listOf("g0000000001", "g0000000002"), v.goals.map { it.id })
        val g = v.goals.first()
        assertEquals("insulate the garage before winter", g.text)
        assertEquals("active", g.status)
        assertEquals(
            listOf(
                Goals.Step("contact 3 installers", "this week", false),
                Goals.Step("pick one and book it", "", false),
            ),
            g.plan,
        )
        assertEquals(Goals.Limits(300, 7, 20, 40), v.limits)
        // Not the list at all: null, never an empty list that reads as "no goals".
        assertNull(Goals.parse(obj("""{"ok":true}""")))
        assertTrue(Goals.missing(ApiError.NotFound))
        assertTrue(Goals.missing(ApiError.Server(501, "")))
        assertFalse(Goals.missing(ApiError.NotAvailable))
    }

    @Test
    fun aReadWithNoUsableLimitsStillReadsTheGoals() {
        val v = Goals.parse(obj("""{"ok":true,"goals":[],"limits":{"text":300}}"""))!!
        assertNull(v.limits)
    }

    @Test
    fun oneGoalAndOneAcceptedAnswerReadRight() {
        val one = Goals.parseOne(obj(
            """{"ok":true,"goal":{"id":"g0000000001","text":"x","plan":[{"step":"a","by":"","done":true}],
                "status":"active","created":1,"changed":2}}""",
        ))!!
        assertTrue(one.plan.single().done)
        val accepted = Goals.parseAccepted(obj(
            """{"ok":true,"goal":{"id":"g0000000001","text":"x",
                "plan":[{"step":"a","by":"","done":false}],"status":"active","created":1,"changed":2,
                "checkin":{"id":"s00000000b1","kind":"goal_checkin","state":"waiting","text":"x"}}}""",
        ))!!
        assertEquals("g0000000001", accepted.goal.id)
        assertEquals("waiting", accepted.checkin?.state)
        assertEquals("s00000000b1", accepted.checkin?.id)
        // No checkin at all (an older PC, or a plain read): still a goal, no job.
        assertNull(Goals.parseAccepted(obj("""{"ok":true,"goal":{"id":"g0000000001","text":"x",
            "plan":[{"step":"a","by":"","done":false}],"status":"active","created":1,"changed":2}}""",
        ))?.checkin)
    }

    @Test
    fun theBodiesAreOneRowAndOneAnswerPerRequest() {
        assertEquals("/api/goals", Goals.PATH)
        assertEquals("insulate the garage", obj(Goals.createBody("insulate the garage"))["text"]!!.jsonPrimitive.content)
        assertFalse(obj(Goals.createBody("x")).containsKey("plan"))
        val withPlan = obj(Goals.createBody("x", listOf(Goals.Step("a", "soon", false))))
        val step = withPlan["plan"]!!.jsonArray.single().jsonObject
        assertEquals("a", step["step"]!!.jsonPrimitive.content)
        assertEquals("soon", step["by"]!!.jsonPrimitive.content)
        assertFalse(step["done"]!!.jsonPrimitive.boolean)
        // No plan to keep the draft as it stood: an empty object, never a null "plan".
        assertEquals("{}", Goals.acceptBody())
        val acceptStep = obj(Goals.acceptBody(listOf(Goals.Step("a", "", true))))["plan"]!!
            .jsonArray.single().jsonObject
        assertTrue(acceptStep["done"]!!.jsonPrimitive.boolean)
        val stepBody = obj(Goals.stepBody(1, true))
        assertEquals(1, stepBody["index"]!!.jsonPrimitive.int)
        assertTrue(stepBody["done"]!!.jsonPrimitive.boolean)
        assertEquals("{}", Goals.STOP_BODY)
    }

    @Test
    fun validationMatchesThePcsOwnLimits() {
        assertTrue(Goals.validText("insulate the garage"))
        assertFalse(Goals.validText(""))
        assertFalse(Goals.validText("x".repeat(301)))
        assertTrue(Goals.validText("x".repeat(300)))
        assertTrue(Goals.validBy(""))
        assertFalse(Goals.validBy("x".repeat(41)))
        val onePlan = listOf(Goals.Step("a", "", false))
        assertTrue(Goals.validPlan(onePlan))
        assertFalse(Goals.validPlan(emptyList()))
        assertTrue(Goals.validPlan(List(7) { Goals.Step("step $it", "", false) }))
        assertFalse(Goals.validPlan(List(8) { Goals.Step("step $it", "", false) }))
        assertFalse(Goals.validPlan(listOf(Goals.Step("", "", false))))
    }

    @Test
    fun creatingADraftReadsRight() {
        val ok = Goals.Reply(200, obj(
            """{"ok":true,"goal":{"id":"g0000000001","text":"x","plan":[{"step":"x","by":"","done":false}],
                "status":"draft","created":1,"changed":1}}""",
        ))
        val (started, goal, said) = Goals.createdSaid(ok)
        assertTrue(started)
        assertEquals("draft", goal?.status)
        assertTrue(said.contains("draft"))
        val overflow = Goals.Reply(409, obj(
            """{"ok":false,"error":"there are already 20 goals - stop tracking one before adding another"}""",
        ))
        val (ok2, goal2, said2) = Goals.createdSaid(overflow)
        assertFalse(ok2)
        assertNull(goal2)
        assertEquals("Not changed. There are already 20 goals - stop tracking one before adding another", said2)
        val old = Goals.createdSaid(Goals.Reply(404, null))
        assertFalse(old.first)
        assertEquals(Goals.TOO_OLD, old.third)
    }

    @Test
    fun acceptingReadsTheWaitingCardAndTheRefusals() {
        val waiting = Goals.Reply(200, obj(
            """{"ok":true,"goal":{"id":"g0000000001","text":"x",
                "plan":[{"step":"a","by":"","done":false}],"status":"active","created":1,"changed":2,
                "checkin":{"id":"s00000000b1","kind":"goal_checkin","state":"waiting","text":"x"}}}""",
        ))
        val (ok, accepted, said) = Goals.acceptedSaid(waiting)
        assertTrue(ok)
        assertEquals("waiting", accepted?.checkin?.state)
        assertEquals("Accepted. ${Goals.WAITING}", said)
        val notADraft = Goals.Reply(400, obj("""{"ok":false,"error":"that goal is not waiting to be accepted"}"""))
        val (ok2, _, said2) = Goals.acceptedSaid(notADraft)
        assertFalse(ok2)
        assertEquals("Not changed. That goal is not waiting to be accepted", said2)
        val noScheduler = Goals.Reply(503, obj("""{"ok":false,"error":"the scheduler is not available"}"""))
        assertEquals(Goals.NOT_AVAILABLE, Goals.acceptedSaid(noScheduler).third)
        val gone = Goals.Reply(404, obj("""{"ok":false,"error":"no such goal"}"""))
        val (ok3, _, said3) = Goals.acceptedSaid(gone)
        assertFalse(ok3)
        assertEquals(Goals.ALREADY_GONE, said3)
    }

    @Test
    fun tickingAStepAndStoppingReadRight() {
        val stepped = Goals.Reply(200, obj(
            """{"ok":true,"goal":{"id":"g0000000001","text":"x",
                "plan":[{"step":"a","by":"","done":true}],"status":"active","created":1,"changed":2}}""",
        ))
        val (ok, g, said) = Goals.changedSaid(stepped)
        assertTrue(ok)
        assertTrue(g!!.plan.single().done)
        assertEquals("Done.", said)
        val badIndex = Goals.Reply(400, obj("""{"ok":false,"error":"that is not one of this goal's steps"}"""))
        assertFalse(Goals.changedSaid(badIndex).first)
        val stopped = Goals.Reply(200, obj(
            """{"ok":true,"goal":{"id":"g0000000001","text":"x","plan":[{"step":"a","by":"","done":false}],
                "status":"stopped","created":1,"changed":2}}""",
        ))
        val (ok2, g2, said2) = Goals.changedSaid(stopped, doneWord = "Stopped.")
        assertTrue(ok2)
        assertEquals("stopped", g2?.status)
        assertEquals("Stopped.", said2)
    }

    @Test
    fun theStatusTagAndOrderingMatchTheOwnersWords() {
        assertEquals("Draft", Goals.statusTag("draft"))
        assertEquals("Stopped", Goals.statusTag("stopped"))
        assertEquals("Done", Goals.statusTag("done"))
        assertEquals("", Goals.statusTag("active"))
        val v = Goals.parse(listAnswer)!!
        // The PC already sends newest first; open goals (draft, active) come
        // before closed ones (stopped, done), each keeping that order.
        assertEquals(listOf("g0000000001", "g0000000002"), Goals.ordered(v).map { it.id })
        assertEquals(emptyList<Goals.Goal>(), Goals.ordered(null))
        // Reorders when a closed goal is newer (comes first) than an open
        // one - never just passes the PC's own order straight through.
        fun bare(id: String, status: String) = Goals.Goal(id, "x", listOf(Goals.Step("a", "", false)), status, 1.0, 1.0)
        val mixed = Goals.View(listOf(bare("g1", "stopped"), bare("g2", "active"), bare("g3", "draft")), null)
        assertEquals(listOf("g2", "g3", "g1"), Goals.ordered(mixed).map { it.id })
    }

    @Test
    fun hidingBlanksEveryGoalsAndStepsOwnWords() {
        val v = Goals.parse(listAnswer)!!
        val hidden = Goals.hide(v)
        assertTrue(hidden.goals.all { it.text == Goals.HIDDEN_TEXT })
        assertTrue(hidden.goals.all { g -> g.plan.all { it.step.isEmpty() && it.by.isEmpty() } })
        // Ids, status and done-ness are not words: they still drive the UI blind.
        assertEquals(v.goals.map { it.id to it.status }, hidden.goals.map { it.id to it.status })
        assertEquals(v.goals[0].plan.map { it.done }, hidden.goals[0].plan.map { it.done })
    }

    @Test
    fun aGoalIdIsGAndTenHexDigits() {
        assertTrue(Goals.validId("g0123456789"))
        assertFalse(Goals.validId("s0123456789")) // a schedule job id, not a goal id
        assertFalse(Goals.validId("g012345678")) // too short
        assertFalse(Goals.validId(null))
    }

    @Test
    fun theWiringHoldsEveryWriteOnAStaleLinkAndValidatesTheId() {
        val main = "jarvis-client/app/src/main/java/com/jarvis/client"
        val rt = repoFile("$main/JarvisRuntime.kt").readText()
        for (fn in listOf("createGoal(", "acceptGoal(", "setGoalStep(", "stopGoal(")) {
            val start = rt.indexOf("suspend fun $fn")
            assertTrue("JarvisRuntime.$fn not found", start >= 0)
            val body = rt.substring(start, rt.indexOf("\n    }\n", start))
            assertTrue("$fn does not check actionBlocker()", body.contains("actionBlocker()"))
        }
        assertTrue(rt.contains("if (!com.jarvis.client.net.Goals.validId(id))"))
        // Accepting refreshes the approval queue at once, rather than waiting
        // for the next `pending` event.
        val acceptStart = rt.indexOf("suspend fun acceptGoal(")
        val acceptBody = rt.substring(acceptStart, rt.indexOf("\n    }\n", acceptStart))
        assertTrue(acceptBody.contains("refreshPending()"))
        val api = repoFile("$main/net/JarvisApi.kt").readText()
        assertTrue(api.contains("suspend fun goals(): ApiResult<JsonObject> = probe(Goals.PATH)"))
        assertTrue(api.contains("suspend fun goalsWrite(path: String, json: String): ApiResult<Goals.Reply>"))
    }

    @Test
    fun theSectionIsOnBrainBesideComingUpAndNeverBuildsItsOwnApprovalFlow() {
        val main = "jarvis-client/app/src/main/java/com/jarvis/client"
        val brain = repoFile("$main/ui/screens/BrainScreen.kt").readText()
        assertTrue(brain.indexOf("item(key = \"coming-up\")") in 0 until brain.indexOf("item(key = \"goals\")"))
        assertTrue(brain.contains("GoalsSection("))
        val plate = repoFile("$main/ui/screens/GoalsPlate.kt").readText()
        // Accept and Stop tracking call JarvisRuntime directly - there is no
        // separate "approve" button of Goals' own; the one card Accept can
        // raise is answered only through the ordinary approval queue.
        assertTrue(plate.contains("JarvisRuntime.acceptGoal("))
        assertTrue(plate.contains("JarvisRuntime.stopGoal("))
        assertTrue(plate.contains("JarvisRuntime.setGoalStep("))
        assertFalse("Goals must never approve its own card", plate.contains("JarvisRuntime.decide("))
        assertFalse("Stop tracking must have no confirm dialog", plate.contains("confirmStop"))
    }

    @Test
    fun aGoalCheckinRowOffersNoButtonsOfItsOwnOnComingUp() {
        // Pausing or deleting it there, directly, would leave the goal
        // `active` with no way to bring the check-in back - see Goals.kt's
        // own doc comment. Stop tracking, on the goal itself, is the one
        // control that takes both down together.
        val waitingJob = Schedule.job(obj(
            """{"id":"s00000000b1","kind":"goal_checkin","state":"waiting","text":"insulate the garage"}""",
        ))!!
        assertEquals(emptyList<String>(), Schedule.actionsOf(waitingJob))
        val activeJob = Schedule.job(obj(
            """{"id":"s00000000b1","kind":"goal_checkin","state":"active","text":"insulate the garage"}""",
        ))!!
        assertEquals(emptyList<String>(), Schedule.actionsOf(activeJob))
        assertEquals("goal check-in", Schedule.tag("goal_checkin"))
    }

    // ---------------------------------------- step locks (section 101) ----

    private val fixture: JsonObject = run {
        val text = requireNotNull(javaClass.classLoader?.getResource("contract/projects-cases.json")) {
            "contract/projects-cases.json is missing - run tools/gen_projects_cases.py"
        }.readText()
        obj(text)
    }
    private val goalCases get() = fixture["goal_cases"]!!.jsonObject

    /** A case's answer: its `body`, or the case itself when it is a bare body. */
    private fun answer(name: String): JsonObject {
        val c = goalCases[name]!!.jsonObject
        return (c["body"] as? JsonObject) ?: c
    }

    private fun refusal(name: String): Goals.Reply {
        val c = goalCases[name]!!.jsonObject
        return Goals.Reply(c["status"]!!.jsonPrimitive.int, c["body"]!!.jsonObject)
    }

    @Test
    fun theLockWordsAreThePcsKeyForKey() {
        val words = fixture["goal_words"]!!.jsonObject
        assertEquals(words.keys, Goals.WORDS.keys)
        for ((k, v) in words) assertEquals(k, v.jsonPrimitive.content, Goals.WORDS[k])
        val limits = fixture["goal_limits"]!!.jsonObject
        assertEquals(limits["needs"]!!.jsonPrimitive.int, Goals.MAX_NEEDS)
        assertEquals(limits["steps"]!!.jsonPrimitive.int, Goals.MAX_STEPS)
        assertEquals(limits["step_ids"]!!.jsonArray.map { it.jsonPrimitive.content }, Goals.STEP_IDS)
        // The list read carries the same words and limits.
        assertEquals(fixture["goal_words"], answer("list")["words"])
        assertEquals(Goals.MAX_NEEDS, Goals.parse(answer("list"))!!.limits!!.needs)
    }

    @Test
    fun aLockedStepIsReadAsSentAndItsTickIsOff() {
        val plan = Goals.parseOne(answer("created"))!!.plan
        val first = plan[0]
        val second = plan[1]
        assertEquals("s1", first.id)
        assertEquals("open", first.state)
        assertEquals("5k time", first.measureName)
        assertNotNull(first.measure)
        assertEquals("bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb", first.measure!!.bench)
        assertTrue(second.locked)
        assertFalse(second.met)
        assertEquals(listOf("s1"), second.needs)
        assertEquals(listOf("s1"), second.waitingOn)
        assertEquals("after: \"Get the 5k under 30\"", second.lockWords)
        // The tick is off for a locked step; an open one can be ticked.
        assertFalse(Goals.canTick(second))
        assertTrue(Goals.canTick(first))
        // "<step>, locked, after: <steps>"
        assertEquals("Enter the race, locked, after: \"Get the 5k under 30\"", Goals.spoken(second, second.step))
        assertEquals("Get the 5k under 30", Goals.spoken(first, first.step))
    }

    @Test
    fun reachedByNumberIsNotATickAndKeepsTheTickButton() {
        val first = Goals.parseOne(answer("number_reached"))!!.plan[0]
        assertEquals("met_by_number", first.state)
        assertTrue(first.met)
        assertFalse("reaching a target never ticks the step", first.done)
        assertTrue(first.reached)
        assertEquals("The number reached its target: 29.5 min (target 30 min).", first.reachedWords)
        assertTrue(Goals.canTick(first))
        assertTrue(Goals.spoken(first, first.step).endsWith(first.reachedWords))
        val after = Goals.parseOne(answer("first_undone"))!!.plan
        assertTrue(after[1].done)
        assertEquals("done", after[1].state)
        assertEquals(1790000120.0, after[1].doneAt!!, 1e-9)
        assertEquals("open", after[2].state)
    }

    @Test
    fun theRefusalsAreShownAsSent() {
        // A tick on a locked step (a stale screen): the PC's sentence alone.
        val tick = refusal("refuse_tick_locked")
        val (ok, goal, said) = Goals.changedSaid(tick)
        assertFalse(ok)
        assertNull(goal)
        assertEquals(tick.body!!["error"]!!.jsonPrimitive.content, said)
        assertEquals("Do \"Get the 5k under 30\" first, or tick it if it is already done.", said)
        // Saving a plan: the PC's sentence after "Not changed.", nothing altered.
        for (name in listOf("refuse_cycle", "refuse_self", "refuse_too_many", "refuse_unknown")) {
            val r = refusal(name)
            val err = r.body!!["error"]!!.jsonPrimitive.content
            assertEquals(name, "Not changed. $err", Goals.acceptedSaid(r).third)
            assertEquals(name, "Not changed. $err", Goals.createdSaid(r).third)
        }
        assertTrue(Goals.acceptedSaid(refusal("refuse_cycle")).third.contains("in a circle"))
    }

    @Test
    fun anOlderPcsPlainStepStillReadsWithDefaults() {
        val plain = Goals.parseOne(obj(
            """{"ok":true,"goal":{"id":"g0000000001","text":"x","future":1,
                "plan":[{"step":"a","by":"","done":true,"surprise":{"x":1}}],"status":"active","created":1,"changed":2}}""",
        ))!!.plan.single()
        assertEquals(Goals.Step("a", "", true), plain)
        assertFalse(plain.locked)
        assertEquals("", plain.id)
        // Junk in the new fields is dropped, not guessed.
        val junk = Goals.parseOne(obj(
            """{"ok":true,"goal":{"id":"g0000000001","text":"x","status":"draft","created":1,"changed":2,
                "plan":[{"step":"a","by":"","done":false,"needs":["s2","../x",7],"measure":{"project":"no","bench":"no"},
                         "state":"locked","waiting_on":"s2","done_at":"soon"}]}}""",
        ))!!.plan.single()
        assertEquals(listOf("s2"), junk.needs)
        assertNull(junk.measure)
        assertTrue(junk.waitingOn.isEmpty())
        assertNull(junk.doneAt)
        assertTrue(junk.locked)
    }

    @Test
    fun aSavedPlanSendsOnlyTheStoredFields() {
        val plan = Goals.parseOne(answer("created"))!!.plan
        val sent = obj(Goals.acceptBody(plan))["plan"]!!.jsonArray
        assertEquals(3, sent.size)
        val stored = setOf("id", "step", "by", "done", "needs", "measure")
        for (st in sent) assertEquals(stored, st.jsonObject.keys)
        val second = sent[1].jsonObject
        assertEquals("s2", second["id"]!!.jsonPrimitive.content)
        assertEquals(listOf("s1"), second["needs"]!!.jsonArray.map { it.jsonPrimitive.content })
        assertEquals(JsonNull, second["measure"])
        val measure = sent[0].jsonObject["measure"]!!.jsonObject
        assertEquals("aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa", measure["project"]!!.jsonPrimitive.content)
        // A new step has no id yet; done_at and the computed words are never sent.
        val fresh = obj(Goals.createBody("x", listOf(Goals.Step("a", "", false))))["plan"]!!.jsonArray.single().jsonObject
        assertFalse(fresh.containsKey("id"))
        assertFalse(fresh.containsKey("done_at"))
        assertFalse(fresh.containsKey("lock_words"))
    }

    @Test
    fun theDraftEditorKeepsIdsAndStopsAtThreeNeeds() {
        var plan = listOf(
            Goals.Step("A", "", false, id = "s1"),
            Goals.Step("B", "", false, id = "s2", needs = listOf("s1")),
            Goals.Step("C", "", false, id = "s3", needs = listOf("s2", "s1")),
        )
        // A new step gets a free id.
        assertEquals("s4", Goals.newStep(plan).id)
        assertEquals("s1", Goals.newStep(plan.drop(1)).id)
        // Picking: never itself, never a fourth.
        assertEquals(plan, Goals.toggleNeed(plan, 0, "s1"))
        plan = plan + Goals.newStep(plan) + Goals.newStep(plan + Goals.newStep(plan))
        var d = plan.map { it }
        d = Goals.toggleNeed(d, 2, "s4")
        assertEquals(listOf("s2", "s1", "s4"), d[2].needs)
        assertEquals("a fourth is not added", d, Goals.toggleNeed(d, 2, "s5"))
        assertEquals(listOf("s2", "s1"), Goals.toggleNeed(d, 2, "s4")[2].needs)
        // Deleting a step takes its id out of every other step's needs, and says so.
        val (rest, touched) = Goals.removeStep(plan, 0)
        assertTrue(touched)
        assertTrue(rest.none { "s1" in it.needs })
        assertEquals(listOf("s2"), rest.first { it.id == "s3" }.needs)
        assertFalse(Goals.removeStep(plan, 3).second)
        // A measure is set and cleared.
        val m = Goals.Measure("a".repeat(32), "b".repeat(32))
        assertEquals(m, Goals.setMeasure(plan, 0, m)[0].measure)
        assertNull(Goals.setMeasure(Goals.setMeasure(plan, 0, m), 0, null)[0].measure)
        assertEquals("Step 6", Goals.label(plan, 5))
        assertEquals("A", Goals.label(plan, 0))
    }

    @Test
    fun onlyBenchmarksWithATargetCanBeFollowed() {
        fun bench(id: String, kind: String, target: Double?, better: String?) = Projects.Bench(
            id = id, name = "b$id", kind = kind, unit = "min", better = better, target = target,
            sensitive = false, keepOnScreen = false, keepOnScreenWords = "", markedByYou = false,
            unmark = "", unmarkWaiting = false, unmarkLast = "", results = 0, latest = null, said = "",
            targetReached = false, command = "", notRunnableWhy = "", points = null,
        )
        val p = "a".repeat(32)
        val project = Projects.Project(
            id = p, name = "Run", kind = "life", instructions = "", notes = emptyList(), folder = null,
            shareable = false, shareableWaiting = false, shareableLast = "", workListTitle = null,
            benchmarks = 3,
            benchList = listOf(
                bench("b".repeat(32), "number", 30.0, "lower"),
                bench("c".repeat(32), "number", null, "lower"),
                bench("d".repeat(32), "command", 30.0, "lower"),
            ),
            maxInstructions = 0,
        )
        val options = Goals.measureOptions(listOf(project))
        assertEquals(1, options.size)
        assertEquals("Run: b${"b".repeat(32)}", options.single().label)
        assertEquals(Goals.Measure(p, "b".repeat(32)), options.single().measure)
    }

    @Test
    fun hidingKeepsTheStateButNotTheWords() {
        val v = Goals.parse(answer("list"))!!
        val hidden = Goals.hide(v)
        val plan = hidden.goals.single().plan
        assertTrue(plan.all { it.lockWords.isEmpty() && it.step.isEmpty() })
        assertEquals(v.goals.single().plan.map { it.state }, plan.map { it.state })
        val secret = Goals.Step("x", "", false, state = "open", reached = true, reachedWords = "69 kg", measureName = "Weight", measureSensitive = true)
        val g = Goals.Goal("g0000000001", "t", listOf(secret), "active", 1.0, 1.0)
        val h = Goals.hide(Goals.View(listOf(g), null)).goals.single().plan.single()
        assertEquals("", h.reachedWords)
        assertEquals("", h.measureName)
    }

    @Test
    fun theTickAnswerIsUntickedWhenTakenBack() {
        val src = repoFile("jarvis-client/app/src/main/java/com/jarvis/client/JarvisRuntime.kt").readText()
        assertTrue(src.contains("doneWord = if (done) \"Done.\" else \"Unticked.\""))
    }

    private fun repoFile(rel: String): File {
        var dir: File? = File(System.getProperty("user.dir") ?: ".").absoluteFile
        while (dir != null) {
            val f = File(dir, rel)
            if (f.isFile) return f
            dir = dir.parentFile
        }
        error("$rel not found above ${System.getProperty("user.dir")}")
    }
}
