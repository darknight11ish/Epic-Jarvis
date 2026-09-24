package com.jarvis.client

import com.jarvis.client.net.ApiResult
import com.jarvis.client.net.Approvals
import com.jarvis.client.net.DesktopWrite
import com.jarvis.client.net.JarvisJson
import com.jarvis.client.net.MemoryCounts
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.jsonObject
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test
import java.io.File

/**
 * Mind's memory counts, in the desktop's words (`brain.js`, `renderMemory`),
 * from `/api/memory/status` - and the learning switch, which waits for a card.
 */
class MemoryCountsTest {

    private fun obj(json: String): JsonObject = JarvisJson.parseToJsonElement(json).jsonObject

    @Test
    fun theCountsAreTheDesktopsRowsInItsOrder() {
        val rows = MemoryCounts.fields(
            obj(
                """{"available":true,"db":"C:\\Users\\me\\memory.db","facts":14,"current":12,"retired":2,
                   "embedder":"hash","semantic":false,"vector_search":false,"unembedded":3,
                   "sleep_time":{"enabled":false,"remind":true}}""",
            ),
        )
        assertEquals(
            listOf(
                "Facts in use" to "12",
                "No longer used" to "2",
                "Embedding" to "hash (matches words only until the real embedding model has downloaded)",
                "Search by meaning" to "off - facts are found by keyword",
                "Waiting to be indexed" to "3",
                "Overnight tidying" to "off (not built yet)",
            ),
            rows,
        )
        assertFalse("the PC's file path is not shown", rows.any { it.second.contains("memory.db") })
    }

    @Test
    fun aHealthyStoreShowsOnlyWhatIsTrue() {
        val rows = MemoryCounts.fields(
            obj(
                """{"available":true,"current":40,"retired":0,"embedder":"bge-small","semantic":true,
                   "vector_search":true,"unembedded":0,"sleep_time":{"enabled":true}}""",
            ),
        )
        assertEquals(
            listOf(
                "Facts in use" to "40",
                "No longer used" to "0",
                "Embedding" to "bge-small",
                "Overnight tidying" to "switched on, but not built yet - nothing runs",
            ),
            rows,
        )
    }

    @Test
    fun anUnavailableStoreOrTextWhereANumberBelongsShowsNothing() {
        assertTrue(MemoryCounts.fields(obj("""{"available":false,"error":"no store"}""")).isEmpty())
        assertTrue(MemoryCounts.fields(obj("""{"current":"lots"}""")).isEmpty())
    }

    @Test
    fun learningIsReadOffTheFactsAnswer() {
        assertEquals(true, MemoryCounts.learning(obj("""{"available":true,"facts":[],"learning":true}""")))
        assertEquals(false, MemoryCounts.learning(obj("""{"learning":false}""")))
        assertNull(MemoryCounts.learning(obj("""{"facts":[]}""")))
        assertTrue(MemoryCounts.learningLine(true).startsWith("Learning is on"))
        assertTrue(MemoryCounts.learningLine(false).startsWith("Learning is off"))
        assertTrue(MemoryCounts.learningLine(null).startsWith("Couldn't tell"))
    }

    /** Walks up from Gradle's working folder (`jarvis-client/app`) to the repository. */
    private fun repoFile(rel: String): File {
        var dir: File? = File(System.getProperty("user.dir") ?: ".").absoluteFile
        while (dir != null) {
            val f = File(dir, rel)
            if (f.isFile) return f
            dir = dir.parentFile
        }
        error("$rel not found above ${System.getProperty("user.dir")}")
    }

    /**
     * The phone's switch is only honest while the PC asks before turning
     * learning on: learning-asks.patch routes the ON through
     * jarvis_learning_switch, whose action is the one the phone watches the
     * queue for. If either name moves, the "waiting" line would never show.
     */
    @Test
    fun thePcAsksBeforeLearningTurnsOn() {
        val patch = repoFile("backend/learning-asks.patch").readText()
        assertTrue(patch.contains("-                return self._send(200, set_learning(body[\"enabled\"]))"))
        assertTrue(patch.contains("+                code, out = jarvis_learning_switch.request(body[\"enabled\"], set_learning)"))
        val module = repoFile("backend/jarvis_learning_switch.py").readText()
        assertTrue(module.contains("ACTION = \"${MemoryCounts.LEARNING_ACTION}\""))
    }

    @Test
    fun onWaitsForTheCardAndNeverSaysOn() {
        val waiting = MemoryCounts.learningSaid(true, DesktopWrite.Outcome.Waiting("anything"))
        assertTrue(waiting, waiting.startsWith("Waiting for your approval to turn learning on."))
        assertTrue(waiting.endsWith(Approvals.WHERE))
        // The PC's real 202 answer, through the same classifier the switch uses.
        val real = DesktopWrite.classify(
            202,
            obj("""{"ok":true,"waiting":true,"enabled":false,"message":"Waiting for your approval."}"""),
        )
        assertTrue(real is ApiResult.Ok && real.value is DesktopWrite.Outcome.Waiting)
        assertEquals("Learning is off. Nothing new will be proposed.",
            MemoryCounts.learningSaid(false, DesktopWrite.Outcome.Done(null)))
        assertEquals("Learning is off.", MemoryCounts.learningSaid(false, DesktopWrite.Outcome.Done("Learning is off.")))
        assertTrue(MemoryCounts.learningSaid(true, DesktopWrite.Outcome.Refused("It must be 'ask'."))
            .startsWith("Not changed."))
    }

    @Test
    fun theCardInTheQueueIsFoundByItsAction() {
        assertTrue(MemoryCounts.learningCardWaiting(listOf(null, "switch_model", "learning_enable")))
        assertFalse(MemoryCounts.learningCardWaiting(listOf(null, "switch_model")))
        assertFalse(MemoryCounts.learningCardWaiting(emptyList()))
        assertEquals("{\"enabled\":true}", MemoryCounts.learningBody(true))
        assertEquals("{\"enabled\":false}", MemoryCounts.learningBody(false))
    }

    @Test
    fun theOffLineSaysTurningOnAsks() {
        assertTrue(MemoryCounts.learningLine(false).contains("asks you first"))
        assertFalse(MemoryCounts.learningLine(false).contains("your PC does not ask yet"))
    }
}
