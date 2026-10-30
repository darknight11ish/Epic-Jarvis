package com.jarvis.client

import com.jarvis.client.net.ApiError
import com.jarvis.client.net.ApiResult
import com.jarvis.client.net.JarvisJson
import com.jarvis.client.net.JobRecord
import com.jarvis.client.net.Jobs
import com.jarvis.client.net.parseListBody
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.booleanOrNull
import kotlinx.serialization.json.jsonObject
import kotlinx.serialization.json.jsonPrimitive
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNotEquals
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test

/**
 * The phone's half of Long Fuse's way in and way out (2026-10-30,
 * `backend/jobs-routes.patch`; docs/JARVIS-API.md section 169).
 *
 * What is held here, in the order the owner meets it:
 *
 *  * the GET body the Work pane reads - the rows, the grants joined by job id,
 *    `ticking` and `status.handlers` - including the body an OLDER PC sends,
 *    which must not read as "nothing is registered";
 *  * the two request bodies, letter for letter, with the owner's words escaped
 *    and NO capability frozen;
 *  * every sentence a start or an answer can produce, including the PC's own
 *    refusals (a second tap, a missing route, a stopped heartbeat);
 *  * the wiring that makes it reachable at all: the section drawn on Brain, the
 *    two runtime calls held on a stale link, and the two writes using the
 *    "explained refusal" transport rather than losing the PC's sentence.
 */
class BackgroundJobsTest {

    // ------------------------------------------------------------ fixtures ----

    /** The exact body `jobs-routes.patch` makes `GET /api/jobs` send. */
    private val realGetBody = """
        {"available": true,
         "jobs": [
           {"id": "j1", "label": "watch the jarvis repo", "state": "waiting_approval",
            "progress": null, "capabilities": [], "private": false,
            "handler": "watch_github", "caps": [], "tainted": false, "created": 1700000000},
           {"id": "j2", "label": "tidy the notes", "state": "running",
            "capabilities": ["memory.write"], "handler": "watch_github", "created": 1700000001}
         ],
         "grants": [
           {"id": "g1", "job_id": "j1", "action": "send_email", "state": "pending",
            "created": 1700000010, "label": "watch the jarvis repo", "handler": "watch_github"}
         ],
         "ticking": true,
         "status": {"enabled": true, "handlers": ["watch_github"],
                    "counts": {"running": 1, "waiting_approval": 1},
                    "config": {"approval_retry_seconds": 30}}}
    """.trimIndent()

    private fun feed(body: String): Jobs.Feed =
        (parseListBody(body, Jobs.Feed.serializer(), emptyList()) as ApiResult.Ok).value

    private fun read(body: String): Jobs.Read = Jobs.readOf(parseListBody(
        body, Jobs.Feed.serializer(), emptyList(),
    ))

    private fun reply(json: String): JsonObject = JarvisJson.parseToJsonElement(json).jsonObject

    private fun wordsOf(s: Jobs.Said): String = when (s) {
        is Jobs.Said.Landed -> s.words
        is Jobs.Said.Refused -> s.words
    }

    // ------------------------------------------------------------ the read ----

    @Test
    fun `the whole body the routes patch sends reads`() {
        val f = feed(realGetBody)
        assertEquals(listOf("j1", "j2"), f.jobs.map { it.id })
        assertEquals(listOf("watch_github"), f.status.handlers)
        assertEquals(true, f.ticking)
        assertEquals("send_email", f.grantFor("j1")?.action)
        // The one job with a pending grant is parked and NEEDS its two buttons;
        // the running one is not asking anything.
        assertFalse(f.answered(f.jobs[0]))
        assertFalse(f.answered(f.jobs[1]))
    }

    @Test
    fun `a parked job is joined to ITS grant, never to another job's`() {
        // Two parked jobs at once must never have their buttons swapped: the
        // answer names the grant's own job, so the match is by job id.
        val two = feed(
            """{"available": true, "ticking": true, "status": {"handlers": ["watch_github"]},
                "jobs": [{"id": "a", "state": "waiting_approval"},
                         {"id": "b", "state": "waiting_approval"},
                         {"id": "c", "state": "waiting_approval"}],
                "grants": [{"id": "ga", "job_id": "a", "action": "send_email"},
                           {"id": "gb", "job_id": "b", "action": "fs.write"}]}""",
        )
        assertEquals("send_email", two.grantFor("a")?.action)
        assertEquals("fs.write", two.grantFor("b")?.action)
        assertNull("c is parked with no grant left", two.grantFor("c"))
        // c has already been answered; a and b have not.
        assertTrue(two.answered(two.jobs[2]))
        assertFalse(two.answered(two.jobs[0]))
    }

    @Test
    fun `a decided grant is not offered twice`() {
        // `pending_grants()` only ever sends state=pending, so this is belt and
        // braces: a grant that is already granted must not draw two more buttons.
        val f = feed(
            """{"available": true, "ticking": true, "status": {"handlers": ["h"]},
                "jobs": [{"id": "j1", "state": "waiting_approval"}],
                "grants": [{"id": "g1", "job_id": "j1", "action": "send_email",
                            "state": "granted"}]}""",
        )
        assertNull(f.grantFor("j1"))
        assertTrue(f.answered(f.jobs[0]))
    }

    @Test
    fun `an older PC keeps its read-only list and says which patch it needs`() {
        // Before jobs-routes.patch the GET had no `grants` and no `ticking`. That
        // absence is the ONLY reliable way to tell an older backend from one that
        // simply has no handlers today - and saying "nothing is registered" here
        // would be a guess about a PC that has just proved it does not tell us.
        val old = """{"available": true, "jobs": [{"id": "j1", "state": "running"}],
                      "status": {"running": 1}}"""
        val r = read(old)
        assertTrue("an old body must not read as a startable board", r is Jobs.Read.OlderBackend)
        // The job list it always had is still shown - this screen was read-only
        // before the slice, and it must not go blank because a route is missing.
        assertEquals("j1", Jobs.feedOf(r)?.jobs?.single()?.id)
        val line = Jobs.readLine(r)!!
        assertTrue(line, line.contains("apply-patches.ps1"))
    }

    @Test
    fun `a route that is not there is the same older PC, never an empty list`() {
        // 404/503 on the GET means the route itself is absent.
        val gone = Jobs.readOf(ApiResult.Failed(ApiError.NotFound))
        assertTrue(gone is Jobs.Read.OlderBackend)
        assertEquals(Jobs.UPDATE, Jobs.readLine(gone))

        val off = Jobs.readOf(ApiResult.Failed(ApiError.NotAvailable))
        assertTrue(off is Jobs.Read.OlderBackend)
    }

    @Test
    fun `available false is not an empty job list`() {
        // The parse helper refuses it before it can read as "no jobs": a queue
        // that is switched off and a queue that is empty are different facts.
        val refused = parseListBody("""{"available": false}""", Jobs.Feed.serializer(), emptyList())
        assertTrue(refused is ApiResult.Failed)
        assertEquals(ApiError.NotAvailable, (refused as ApiResult.Failed).error)
        val r = Jobs.readOf(refused)
        assertTrue(r is Jobs.Read.OlderBackend)
    }

    @Test
    fun `a failed read says why in plain words`() {
        val r = Jobs.readOf(ApiResult.Failed(ApiError.Server(500, "Traceback...")))
        assertTrue(r is Jobs.Read.Failed)
        assertTrue(Jobs.readLine(r)!!.isNotBlank())
    }

    @Test
    fun `a parked job on an older PC is not called answered`() {
        // With no grants list at all, "no grant" is not evidence of anything.
        val old = Jobs.Feed(jobs = listOf(JobRecord(id = "j1", state = "waiting_approval")))
        assertNull(old.grants)
        assertFalse(old.answered(old.jobs[0]))
    }

    // ---------------------------------------------------- the request bodies ----

    @Test
    fun `the two bodies are the contract's, letter for letter`() {
        assertEquals(
            """{"kind":"watch_github","text":"watch the jarvis repo","needs":[]}""",
            Jobs.startBody("watch_github", "watch the jarvis repo"),
        )
        assertEquals("""{"id":"j1","approved":true}""", Jobs.answerBody("j1", true))
        assertEquals("""{"id":"j1","approved":false}""", Jobs.answerBody("j1", false))
    }

    @Test
    fun `the owner's words are escaped into the body, not pasted`() {
        val words = "watch \"my\" repo \\ notes\nand more"
        val obj = JarvisJson.parseToJsonElement(Jobs.startBody("watch_github", words)).jsonObject
        // The exact words survive a JSON round trip - nothing is lost or broken
        // out of its field.
        assertEquals(words, obj["text"]!!.jsonPrimitive.content)
        assertEquals("watch_github", obj["kind"]!!.jsonPrimitive.content)
    }

    @Test
    fun `starting freezes NO capability`() {
        // The desktop's form sends `needs: []` on purpose: the job begins with
        // nothing and parks on its first need, where the owner answers one
        // question at a time. Nothing on this screen is a capability picker.
        val body = Jobs.startBody("watch_github", "x")
        assertTrue(body.contains("\"needs\":[]"))
        assertFalse("a capability was frozen", body.contains("\"needs\":[\""))
        val obj = JarvisJson.parseToJsonElement(body).jsonObject
        assertEquals(0, (obj["needs"] as kotlinx.serialization.json.JsonArray).size)
    }

    @Test
    fun `approved is a real JSON boolean, both ways`() {
        // "approved": "false" is a string and would read as a yes on the server;
        // the server refuses it rather than guessing, and this side never sends it.
        for (yes in listOf(true, false)) {
            val obj = JarvisJson.parseToJsonElement(Jobs.answerBody("j1", yes)).jsonObject
            val p = obj["approved"]!!.jsonPrimitive
            assertTrue("approved was not a JSON boolean", p.isString.not())
            assertEquals(yes, p.booleanOrNull)
        }
    }

    @Test
    fun `an answer can only carry one job and one word`() {
        // No list form, no "always": a standing rule is exactly what this route
        // must never be able to write.
        val body = Jobs.answerBody("j1", true)
        val obj = JarvisJson.parseToJsonElement(body).jsonObject
        assertEquals(setOf("id", "approved"), obj.keys)
        for (forbidden in listOf("always", "allow_all", "needs", "rule")) {
            assertFalse(body.contains(forbidden))
        }
        assertFalse(Jobs.ALLOW_ONCE.contains("always", ignoreCase = true))
    }

    // ------------------------------------------------- the form is not offered ----

    @Test
    fun `the form is replaced by the server's own reason when it could not work`() {
        assertNull(Jobs.startProblem(null))
        assertNull(
            Jobs.startProblem(Jobs.Feed(ticking = true, status = Jobs.Status(listOf("h")))),
        )
        assertEquals(
            Jobs.NO_KINDS,
            Jobs.startProblem(Jobs.Feed(ticking = true, status = Jobs.Status(emptyList()))),
        )
        assertEquals(
            Jobs.HEARTBEAT_OFF,
            Jobs.startProblem(Jobs.Feed(ticking = false, status = Jobs.Status(listOf("h")))),
        )
        // The words are the desktop's fact, said plainly: nothing to start, and a
        // job that would never run.
        assertTrue(Jobs.NO_KINDS.contains("nothing to start"))
        assertTrue(Jobs.HEARTBEAT_OFF.contains("never run"))
        // ...and neither promises a job was started or says anything was approved.
        for (line in listOf(Jobs.NO_KINDS, Jobs.HEARTBEAT_OFF)) {
            assertFalse(line.contains("approved", ignoreCase = true))
        }
    }

    // ------------------------------------------------------- what a start said ----

    @Test
    fun `a start that landed says what happens next, not that it has finished`() {
        val landed = Jobs.startSaid(reply("""{"ok": true, "id": "j9"}"""))
        assertTrue(landed is Jobs.Said.Landed)
        val words = wordsOf(landed)
        assertEquals(Jobs.STARTED, words)
        assertTrue(words, words.contains("next background check"))
        // It approves nothing and does not claim the work is done.
        assertFalse(words.contains("finished", ignoreCase = true))
        assertFalse(words.contains("approved", ignoreCase = true))
    }

    @Test
    fun `a start the PC refused keeps the PC's own sentence`() {
        val refusal = "the background heartbeat is off, so a job created now would never run"
        val refused = Jobs.startSaid(reply("""{"ok": false, "available": false, "error": "$refusal"}"""))
        assertTrue(refused is Jobs.Said.Refused)
        assertEquals(refusal, wordsOf(refused))
    }

    @Test
    fun `a refusal with no sentence is never left blank`() {
        val nobodySaid = Jobs.startSaid(reply("""{"ok": false}"""))
        assertEquals(Jobs.START_REFUSED, wordsOf(nobodySaid))
        val answer = Jobs.answerSaid(reply("""{"ok": false}"""))
        assertEquals(Jobs.ANSWER_REFUSED, wordsOf(answer))
    }

    @Test
    fun `a missing route names the patch to run`() {
        for (e in listOf(ApiError.NotFound, ApiError.NotAvailable)) {
            val start = Jobs.startSaid(null, e)
            assertTrue(start is Jobs.Said.Refused)
            assertTrue(wordsOf(start).contains("apply-patches.ps1"))
            assertEquals(Jobs.UPDATE, wordsOf(Jobs.answerSaid(null, e)))
        }
    }

    @Test
    fun `a link failure is in plain words, not a raw exception`() {
        val down = Jobs.startSaid(null, ApiError.Unreachable("java.net.SocketTimeoutException: 30000"))
        assertTrue(down is Jobs.Said.Refused)
        val words = wordsOf(down)
        assertTrue(words.isNotBlank())
        assertFalse("the raw exception leaked to the screen", words.contains("java.net"))
    }

    // ------------------------------------------------------ what an answer said ----

    @Test
    fun `Allow once says it is one use and is spent by it`() {
        val landed = Jobs.answerSaid(
            reply("""{"ok": true, "grant": {"id": "g1", "action": "send_email",
                     "state": "granted", "decided_by": "hud"}, "waiting": [], "job": {"id": "j1"}}"""),
        )
        assertTrue(landed is Jobs.Said.Landed)
        assertEquals(Jobs.ALLOWED_ONCE, wordsOf(landed))
        assertTrue(wordsOf(landed).contains("spent by the one use"))
    }

    @Test
    fun `No stops that job and is not a rule about the action`() {
        val no = Jobs.answerSaid(
            reply("""{"ok": true, "grant": {"id": "g1", "action": "send_email",
                     "state": "denied", "decided_by": "hud"}, "waiting": [], "stopped": true,
                     "job": {"id": "j1", "state": "failed"}}"""),
        )
        assertTrue("a No is an answer, not a failure", no is Jobs.Said.Landed)
        assertEquals(Jobs.ANSWERED_NO, wordsOf(no))
        assertTrue(wordsOf(no).contains("stops here"))
        assertTrue("the next job asks again", wordsOf(no).contains("asks again"))
    }

    @Test
    fun `a second tap keeps the PC's own reason`() {
        val reason = "that grant has already been answered; nothing changed"
        val second = Jobs.answerSaid(reply("""{"ok": false, "reason": "already_answered", "error": "$reason"}"""))
        assertTrue(second is Jobs.Said.Refused)
        assertEquals(reason, wordsOf(second))
    }

    @Test
    fun `an answered job says it carries on at the next check`() {
        assertTrue(Jobs.ANSWERED_LINE.contains("next background check"))
        // The mobile sentence must not read as "done": a Yes only marks the grant.
        assertFalse(Jobs.ANSWERED_LINE.contains("finished", ignoreCase = true))
    }

    // ------------------------------------------------------------- the words ----

    @Test
    fun `the question names the action in the phone's own card words`() {
        val line = Jobs.wantLine(Jobs.Grant(id = "g1", jobId = "j1", action = "send_email"))
        // CardWords.fallbackTitle is the phone's existing wording for a card with
        // no title, so this reads like every other approval on this phone.
        assertTrue(line, line.contains("\"send email\""))
        assertTrue(line, line.contains("Jarvis wants your OK"))
        assertTrue(line, line.endsWith(Jobs.ONE_ANSWER))
        assertTrue(line, line.contains("this job only"))
        // A missing action is still a sentence, never "Allow once: " with nothing.
        assertTrue(Jobs.wantLine(Jobs.Grant(action = "")).isNotBlank())
    }

    @Test
    fun `every state is said in plain words, and an unknown one passes through`() {
        assertEquals("waiting on you", Jobs.stateWords("waiting_approval"))
        assertEquals("waiting", Jobs.stateWords("queued"))
        assertEquals("running", Jobs.stateWords("running"))
        assertEquals("done", Jobs.stateWords("done"))
        assertEquals("stopped", Jobs.stateWords("failed"))
        assertEquals("cancelled", Jobs.stateWords("cancelled"))
        assertEquals("something-new", Jobs.stateWords("something-new"))
        // The raw machine name never reaches the owner for a state we know.
        assertNotEquals("waiting_approval", Jobs.stateWords("waiting_approval"))
    }

    // ------------------------------------------------------------- the wiring ----

    private val main = "jarvis-client/app/src/main/java/com/jarvis/client/"
    private val net = main + "net/"

    @Test
    fun `the two routes are named where parity can see them`() {
        // tools/check_parity.py reads the phone's main sources, comments stripped:
        // a route only counts as called when its path is really in this tree.
        val jobs = SourceFile.read(net + "Jobs.kt")
        assertTrue(jobs.contains("/api/jobs/answer"))
        assertTrue(jobs.contains("PATH = \"/api/jobs\""))
        assertTrue(jobs.contains("ANSWER_PATH = \"/api/jobs/answer\""))
    }

    @Test
    fun `both writes use the transport that keeps the PC's own sentence`() {
        // postExplained returns the PC's body on an answered refusal. postJson
        // would turn a 409 into a bare status number and lose "already answered".
        val api = SourceFile.read(net + "JarvisApi.kt")
        assertTrue(api, api.contains("postExplained(Jobs.PATH"))
        assertTrue(api, api.contains("postExplained(Jobs.ANSWER_PATH"))
        assertTrue("the whole GET body is read, not just its rows", api.contains("jobsFeed()"))
        assertTrue(api.contains("Jobs.Feed.serializer()"))
    }

    @Test
    fun `both writes are held while the link is not confirmed live`() {
        val runtime = SourceFile.read(main + "JarvisRuntime.kt")
        for (name in listOf("startJob", "answerJob")) {
            val from = runtime.indexOf("suspend fun $name(")
            assertTrue("JarvisRuntime.$name is gone", from >= 0)
            val body = runtime.substring(from, runtime.indexOf("\n    suspend fun ", from + 10)
                .takeIf { it > 0 } ?: runtime.length)
            assertTrue("$name is not held on a stale link (rule 4)", body.contains("actionBlocker()"))
        }
        assertTrue(runtime.contains("Jobs.Said.Refused(it)"))
    }

    @Test
    fun `the Work pane draws the controls, in the existing jobs plate`() {
        val screen = SourceFile.read(main + "ui/screens/BrainScreen.kt")
        // The section is the SAME plate key as before, so every link, jump and
        // menu entry that names it still lands here.
        assertTrue(screen.contains("plate(\"jobs\", drawn = { true })"))
        assertTrue(screen.contains("JobsSection(canAct = canAct)"))
        // The old gate made the plate invisible while there were no jobs - which
        // also made starting the FIRST job impossible from this phone.
        assertFalse("the plate is still hidden when there are no jobs", screen.contains("jobs.isNotEmpty()"))

        val plate = SourceFile.read(main + "ui/screens/JobsPlate.kt")
        assertTrue(plate.contains("JarvisRuntime.startJob("))
        assertTrue(plate.contains("JarvisRuntime.answerJob("))
        // Exactly two answers, and the deny/approve order every screen uses.
        assertTrue(plate.contains("Refuse(Jobs.NO"))
        assertTrue(plate.contains("Affirm(Jobs.ALLOW_ONCE"))
        // Counted in the CODE, not the prose: the doc comment says the words
        // "Always allow" out loud precisely because there is no such control.
        assertEquals(
            "a third answer crept in",
            1,
            Regex("""\bAffirm\(""").findAll(plate).count(),
        )
        assertEquals("a second No/allow pair crept in", 1, Regex("""\bRefuse\(""").findAll(plate).count())
        // The form offers only the PC's registered bodies.
        assertTrue(plate.contains("status?.handlers"))
        assertTrue(plate.contains("Jobs.startProblem(feed)"))
    }

    @Test
    fun `the record says the phone has it, and keeps no one-sided entry`() {
        // The follow-up rule: a built phone half flips the classification and
        // removes the reason that said it was missing (CLAUDE.md, the audit).
        val parity = SourceFile.read("tools/check_parity.py")
        assertTrue(
            "check_parity.py still does not call /api/jobs/answer ported",
            parity.contains("\"/api/jobs/answer\": (\"ported\""),
        )
        val architecture = SourceFile.read("docs/ARCHITECTURE.md")
        assertFalse(
            "ARCHITECTURE.md still says the phone half is the named next slice",
            architecture.contains("Long Fuse's start/answer loop is the desktop's for now"),
        )
        val api = SourceFile.read("docs/JARVIS-API.md")
        assertTrue(
            "JARVIS-API.md 169.4 still says the phone half is not built",
            api.contains("JobsPlate.kt"),
        )
    }
}
