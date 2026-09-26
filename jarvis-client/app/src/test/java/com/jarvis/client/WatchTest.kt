package com.jarvis.client

import com.jarvis.client.net.ApiError
import com.jarvis.client.net.ApiResult
import com.jarvis.client.net.Approvals
import com.jarvis.client.net.DesktopWrite
import com.jarvis.client.net.JarvisJson
import com.jarvis.client.net.Watch
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.boolean
import kotlinx.serialization.json.int
import kotlinx.serialization.json.jsonObject
import kotlinx.serialization.json.jsonPrimitive
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test

/**
 * Watches on the phone, read the way the desktop's Brain window reads them
 * (`brain.js`, `renderWatch` / `renderWatchReport`; `brain.rs`,
 * `brain_watch_add`). The module behind the routes is on the owner's PC, so
 * these shapes are the desktop's reading of it - see [Watch].
 */
class WatchTest {

    private fun obj(json: String): JsonObject = JarvisJson.parseToJsonElement(json).jsonObject

    @Test
    fun theTopicsAreReadWithTheirCountsAndLines() {
        val v = Watch.read(
            obj(
                """{"topics":2,"tracking":31,"rate_limit":"52 searches left this hour",
                   "waiting_for_you":3,
                   "list":[{"name":"whisper","query":"whisper cpp","checked":1000,"notify":true},
                           {"name":"piper","error":"GitHub said 403"},
                           {"query":"nameless is skipped"}]}""",
            ),
        )
        assertEquals(2, v.topics)
        assertEquals(3, v.waitingForYou)
        assertEquals(listOf("whisper", "piper"), v.list.map { it.name })
        assertEquals("2 topics · 31 projects known · 52 searches left this hour", Watch.headLine(v))
        assertEquals(
            listOf("Searching for: whisper cpp", "checked 1h ago · notify on"),
            Watch.topicLines(v.list[0], nowSeconds = 1000.0 + 3600),
        )
        assertEquals(listOf("GitHub said 403", "never checked · notify off"), Watch.topicLines(v.list[1], 0.0))
    }

    @Test
    fun aQueryThatIsTheNameIsNotRepeated() {
        val t = Watch.Topic("rust", "rust", null, null, false)
        assertEquals(listOf("never checked · notify off"), Watch.topicLines(t, 0.0))
    }

    @Test
    fun agoMatchesTheDesktop() {
        assertEquals("5s ago", Watch.ago(95.0, 100.0))
        assertEquals("2m ago", Watch.ago(0.0, 120.0))
        assertEquals("3h ago", Watch.ago(0.0, 3.0 * 3600))
        assertEquals("2d ago", Watch.ago(0.0, 2.0 * 86400))
        assertEquals("0s ago", Watch.ago(200.0, 100.0))
    }

    @Test
    fun noLicenceStatedIsAWarningNotABlank() {
        val f = Watch.findings(
            obj(
                """{"findings":[
                    {"full_name":"a/b","descr":"fast thing","stars":42,"topic":"whisper","licence":"MIT"},
                    {"name":"c/d","license":"none","archived":true,"note":"one flagged line"},
                    {"full_name":"e/f"}]}""",
            ),
        )
        assertEquals(listOf("a/b", "c/d", "e/f"), f.map { it.title })
        assertEquals("MIT", f[0].licence)
        assertEquals(listOf("fast thing", "★ 42 · topic: whisper · licence: MIT"), Watch.findingLines(f[0]))
        assertNull("\"none\" is no licence", f[1].licence)
        assertEquals(
            listOf("archived · no licence stated - no permission to use it", "scanner: one flagged line"),
            Watch.findingLines(f[1]),
        )
        assertNull(f[2].licence)
    }

    @Test
    fun theReportMayUseItems() {
        assertEquals(1, Watch.findings(obj("""{"items":[{"name":"x/y"}]}""")).size)
        assertTrue(Watch.findings(obj("""{"available":true}""")).isEmpty())
    }

    @Test
    fun theAddBodyIsTheDesktops() {
        val body = obj(Watch.addBody("  whisper ", "", "", " ", notify = false)!!)
        assertEquals(setOf("name", "notify"), body.keys)
        assertEquals("whisper", body["name"]!!.jsonPrimitive.content)
        assertFalse(body["notify"]!!.jsonPrimitive.boolean)

        val full = obj(Watch.addBody("w", "whisper cpp", "100", "C++", notify = true)!!)
        assertEquals("whisper cpp", full["query"]!!.jsonPrimitive.content)
        assertEquals(100, full["min_stars"]!!.jsonPrimitive.int)
        assertEquals("C++", full["language"]!!.jsonPrimitive.content)
        assertTrue(full["notify"]!!.jsonPrimitive.boolean)
    }

    @Test
    fun noNameOrBadStarsSendsNothing() {
        assertNull(Watch.addBody("  ", "q", "", "", false))
        assertNull(Watch.addBody("w", "", "lots", "", false))
        assertNull(Watch.addBody("w", "", "-3", "", false))
    }

    @Test
    fun theRemoveBodyQuotesTheName() {
        assertEquals("a \"b\"", obj(Watch.removeBody("a \"b\"")) ["name"]!!.jsonPrimitive.content)
    }

    @Test
    fun whatIsSaidNeverClaimsMoreThanTheAnswer() {
        assertEquals("Watching rust.", Watch.addSaid("rust", DesktopWrite.Outcome.Done(null)))
        val waiting = Watch.addSaid("rust", DesktopWrite.Outcome.Waiting(null))
        assertTrue(waiting.startsWith("Waiting for your approval"))
        assertTrue("one sentence for where cards are", waiting.contains(Approvals.WHERE))
        assertEquals("Not added. Too many topics.", Watch.addSaid("rust", DesktopWrite.Outcome.Refused("Too many topics.")))
        assertEquals("Forgot rust.", Watch.removeSaid("rust", DesktopWrite.Outcome.Done(null)))
        assertEquals("Marked read.", Watch.seenSaid(DesktopWrite.Outcome.Done(null)))
    }

    @Test
    fun aMissingWatchModuleIsSaidInWords() {
        assertTrue(Watch.failure(ApiError.NotFound)!!.contains("no watch list"))
        assertNull(Watch.failure(ApiError.BadToken))
    }

    // ------------------------------------------------------- DesktopWrite --

    private fun outcome(code: Int, json: String?): ApiResult<DesktopWrite.Outcome> =
        DesktopWrite.classify(code, json?.let(::obj))

    @Test
    fun aPlainSuccessIsDoneWithThePcsWords() {
        assertEquals(ApiResult.Ok(DesktopWrite.Outcome.Done(null)), outcome(200, """{"ok":true}"""))
        assertEquals(ApiResult.Ok(DesktopWrite.Outcome.Done("Watching rust.")), outcome(200, """{"message":"Watching rust."}"""))
        assertEquals(ApiResult.Ok(DesktopWrite.Outcome.Done(null)), outcome(200, null))
    }

    @Test
    fun aCardIsWaitingWhenTheAnswerSaysSoOrIsA202() {
        assertTrue((outcome(200, """{"waiting":true}""") as ApiResult.Ok).value is DesktopWrite.Outcome.Waiting)
        assertTrue((outcome(200, """{"asking":true}""") as ApiResult.Ok).value is DesktopWrite.Outcome.Waiting)
        assertTrue((outcome(200, """{"state":"waiting"}""") as ApiResult.Ok).value is DesktopWrite.Outcome.Waiting)
        assertTrue((outcome(202, """{"ok":true}""") as ApiResult.Ok).value is DesktopWrite.Outcome.Waiting)
    }

    @Test
    fun aNewCardInTheQueueMeansWaitingWhateverTheFieldsSaid() {
        assertEquals(
            DesktopWrite.Outcome.Waiting("x"),
            DesktopWrite.withNewCard(DesktopWrite.Outcome.Done("x"), newCard = true),
        )
        assertEquals(DesktopWrite.Outcome.Done("x"), DesktopWrite.withNewCard(DesktopWrite.Outcome.Done("x"), false))
        val refused = DesktopWrite.Outcome.Refused("no")
        assertEquals(refused, DesktopWrite.withNewCard(refused, true))
    }

    @Test
    fun aRefusalIsShownInThePcsWords() {
        assertEquals(
            ApiResult.Ok(DesktopWrite.Outcome.Refused("No topic named rust.")),
            outcome(200, """{"ok":false,"error":"no topic named rust"}"""),
        )
        assertEquals(
            ApiResult.Ok(DesktopWrite.Outcome.Refused("Need a name.")),
            outcome(400, """{"error":"need a name"}"""),
        )
    }

    @Test
    fun failuresWithoutWordsStayFailures() {
        assertEquals(ApiResult.Failed(ApiError.BadToken), outcome(401, """{"error":"bad token"}"""))
        assertEquals(ApiResult.Failed(ApiError.NotFound), outcome(404, null))
        assertEquals(ApiResult.Failed(ApiError.NotAvailable), outcome(503, "{}"))
        assertEquals(ApiResult.Failed(ApiError.AlreadyHandled), outcome(409, null))
        assertEquals(ApiResult.Failed(ApiError.Server(500, "")), outcome(500, null))
    }
}
