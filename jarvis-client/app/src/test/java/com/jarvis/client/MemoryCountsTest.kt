package com.jarvis.client

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
 * from `/api/memory/status` - and the learning state, read-only.
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
        assertTrue(MemoryCounts.learningLine(null).contains("switch is on your PC"))
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
     * Why the phone has no learning switch: the owner wants turning learning
     * ON to ask first, and the PC's route turns it on at once with no card.
     * When this fails, the PC's route has changed - check whether it now asks,
     * and if so build the phone's switch (and change learningLine).
     */
    @Test
    fun thePcStillSwitchesLearningOnWithoutACard() {
        val route = repoFile("backend/memory-pane.patch").readText()
        assertTrue(route.contains("return self._send(200, set_learning(body[\"enabled\"]))"))
        val setter = repoFile("backend/extraction-wiring.patch").readText()
            .substringAfter("+def set_learning(on: bool) -> dict:").substringBefore("+class ")
        assertTrue("found set_learning", setter.contains("LEARNING_FILE"))
        assertFalse("set_learning raises no card", setter.contains("jarvis_gate") || setter.contains("check("))
    }
}
