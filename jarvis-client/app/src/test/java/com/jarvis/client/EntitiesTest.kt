package com.jarvis.client

import com.jarvis.client.net.ApiError
import com.jarvis.client.net.Entities
import com.jarvis.client.net.JarvisJson
import com.jarvis.client.net.MemoryUsed
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.int
import kotlinx.serialization.json.jsonObject
import kotlinx.serialization.json.jsonPrimitive
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNotNull
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test
import java.io.File
import java.time.ZoneOffset

/**
 * "People and things" on the phone (docs/GALAXY-PANEL-DESIGN.md, option B,
 * decided 2026-09-30; [Entities]). Pure JVM. The words come from the shared
 * fixture `contract/galaxy-cases.json` (tools/gen_galaxy_cases.py, byte-
 * identical to the desktop's copy). The bodies are the ones `entities_view()`
 * and `used_view()` in backend/rebuilt/jarvis_memory.py send.
 */
class EntitiesTest {

    private val doc: JsonObject = run {
        val text = requireNotNull(javaClass.classLoader?.getResource("contract/galaxy-cases.json")) {
            "contract/galaxy-cases.json is missing - run tools/gen_galaxy_cases.py"
        }.readText()
        JarvisJson.parseToJsonElement(text) as JsonObject
    }

    private fun obj(json: String) = JarvisJson.parseToJsonElement(json) as JsonObject

    @Test
    fun everyPanelWordIsTheFixtures() {
        val fixture = doc["words"]!!.jsonObject.mapValues { it.value.jsonPrimitive.content }
        assertEquals(fixture, Entities.WORDS)
        assertEquals(doc["page_size"]!!.jsonPrimitive.int, Entities.PAGE_SIZE)
        assertEquals(doc["max_ids_per_read"]!!.jsonPrimitive.int, MemoryUsed.MAX)
    }

    @Test
    fun numbersAreFilledInByCode() {
        assertEquals("Facts behind this dot (43)", Entities.heading(43))
        assertEquals("Showing 20 of 43", Entities.showingLine(20, 43))
        assertEquals("3 hidden by topic settings", Entities.topicsHiddenLine(3))
        assertNull(Entities.topicsHiddenLine(0))
        assertEquals("1 fact", Entities.factCount(1))
        assertEquals("4 facts", Entities.factCount(4))
    }

    private val entitiesBody = """{"entities": [
        {"id": 1, "name": "Priya", "kind": "person", "also": [], "aliases": ["sister"],
         "fact_ids": [9, 7, 4], "facts": 3},
        {"id": 2, "name": "Biscuit", "kind": "pet", "fact_ids": [8], "facts": 1},
        {"id": 3, "name": "Dan", "kind": "person", "fact_ids": [12, 11, 10, 6], "facts": 4},
        {"id": 4, "name": "Garage", "kind": "project", "fact_ids": [5, 3], "facts": 2},
        {"id": 5, "name": "Lisbon", "kind": "place", "fact_ids": [2], "facts": 1},
        {"id": 6, "name": "Kettle", "kind": null, "fact_ids": [1], "facts": 1},
        {"id": 7, "name": "Odd", "kind": "spaceship", "fact_ids": [13], "facts": 1},
        {"id": 8, "name": "", "kind": "person", "fact_ids": [20], "facts": 1},
        {"id": 9, "name": "Empty", "kind": "person", "fact_ids": [], "facts": 0},
        {"id": 10, "name": "Dup", "kind": "thing", "fact_ids": [30, 30, 0, -2, 31], "facts": 2}
    ], "count": 10, "limit": 500}"""

    @Test
    fun theListIsGroupedByKindBiggestFirst() {
        val list = Entities.parse(obj(entitiesBody))!!
        // A blank name and an entry with no fact ids are dropped; ids kept once, whole and above 0.
        assertEquals(listOf("Priya", "Biscuit", "Dan", "Garage", "Lisbon", "Kettle", "Odd", "Dup"), list.map { it.name })
        assertEquals(listOf(30L, 31L), list.first { it.name == "Dup" }.factIds)
        assertEquals(2, list.first { it.name == "Dup" }.count)
        val groups = Entities.groups(list)
        assertEquals(listOf("People", "Pets", "Places", "Projects", "Things", "Other"), groups.map { it.title })
        assertEquals(listOf("Dan", "Priya"), groups[0].entities.map { it.name })
        assertEquals(listOf("Kettle", "Odd"), groups.last().entities.map { it.name })
        assertEquals("Dan, 4 facts", Entities.rowLine(groups[0].entities[0]))
        assertEquals("Biscuit, 1 fact", Entities.rowLine(groups[1].entities[0]))
    }

    @Test
    fun notTheEntitiesAnswerIsNull() {
        assertNull(Entities.parse(obj("""{"error": "nope"}""")))
        assertEquals(emptyList<Entities.Entity>(), Entities.parse(obj("""{"entities": []}""")))
        assertTrue(Entities.groups(emptyList()).isEmpty())
    }

    @Test
    fun pagesAreTwentyIdsNewestFirstAndNeverOverTheLimit() {
        val ids = (1000L downTo 958L).toList() // 43 ids, newest first
        val e = Entities.Entity("x", "Big", "thing", ids)
        val first = Entities.pageIds(e, 0)
        assertEquals(ids.take(20), first)
        val second = Entities.pageIds(e, 20)
        assertEquals(ids.subList(20, 40), second)
        assertEquals(ids.subList(40, 43), Entities.pageIds(e, 40))
        assertTrue(Entities.hasMore(e, 20))
        assertFalse(Entities.hasMore(e, 43))
        assertTrue(Entities.pageIds(e, 43).isEmpty())
        assertTrue(Entities.pageIds(e, 0, size = 500).size <= MemoryUsed.MAX)
        // Every page is a legal `?ids=` read.
        assertNotNull(MemoryUsed.path(first))
    }

    private val usedBody = """{"facts": [
        {"id": 9, "text": "Priya is getting married in June.", "current": true, "pinned": true,
         "created": 1789000000.0, "valid_to": null, "erased_at": null},
        {"id": 7, "text": "Priya lives in Leeds.", "current": false, "pinned": false,
         "created": 1788000000.0, "valid_to": 1788500000.0, "erased_at": null},
        {"id": 4, "text": "", "current": false, "pinned": false,
         "created": 1787000000.0, "valid_to": null, "erased_at": 1787500000.0},
        {"id": 3, "text": "", "current": true, "pinned": false, "created": 1786000000.0,
         "valid_to": null, "erased_at": null, "left_out": true},
        {"id": 2, "text": "Priya likes jazz.", "current": true, "pinned": false,
         "created": null, "valid_to": null, "erased_at": null}
    ], "missing": [88]}"""

    @Test
    fun rowsShowErasedForgottenPinnedAndDropOffTopicFacts() {
        val view = MemoryUsed.parse(obj(usedBody))!!
        val page = Entities.page(view, ZoneOffset.UTC)
        assertEquals(1, page.hiddenByTopic)
        assertEquals(listOf(9L, 7L, 4L, 2L), page.rows.map { it.id })
        val pinned = page.rows[0]
        assertTrue(pinned.pinned)
        assertFalse(pinned.forgotten)
        assertEquals("Priya is getting married in June.", pinned.text)
        assertEquals("10 Sep 2026", pinned.saved) // 1789000000 s
        assertTrue(page.rows[1].forgotten)
        assertFalse(page.rows[1].erased)
        // An erased fact never carries words, and keeps its date.
        val erased = page.rows[2]
        assertTrue(erased.erased)
        assertEquals("", erased.text)
        assertFalse(erased.forgotten)
        assertEquals("Erased. Only the dates are kept.", Entities.ERASED)
        assertNotNull(erased.saved)
        assertNull(page.rows[3].saved)
        // Current first, then forgotten and erased, each in its newest-first order.
        assertEquals(listOf(9L, 2L, 7L, 4L), Entities.arrange(page.rows).map { it.id })
    }

    @Test
    fun anOffTopicFactsWordsNeverSurvive() {
        val view = MemoryUsed.parse(obj("""{"facts": [
            {"id": 3, "text": "secret words", "current": true, "left_out": true}], "missing": []}"""))!!
        val page = Entities.page(view)
        assertTrue(page.rows.isEmpty())
        assertEquals(1, page.hiddenByTopic)
    }

    @Test
    fun aPcWithoutTheRouteIsSaidNotFaked() {
        assertTrue(Entities.missing(ApiError.NotFound))
        assertTrue(Entities.missing(ApiError.Server(501, "")))
        assertFalse(Entities.missing(ApiError.BadToken))
    }

    @Test
    fun noDateForNothing() {
        assertNull(Entities.dateText(null))
        assertNull(Entities.dateText(0.0))
        assertNull(Entities.dateText(Double.NaN))
    }

    // ------------------------------------------- how it is wired (source) ---

    @Test
    fun itUsesTheTwoExistingReadsAndNothingElse() {
        assertEquals("/api/memory/entities", Entities.PATH)
        val main = "jarvis-client/app/src/main/java/com/jarvis/client"
        val api = repoFile("$main/net/JarvisApi.kt").readText()
        assertTrue(api.contains("suspend fun memoryEntities(): ApiResult<JsonObject> = probe(Entities.PATH)"))
        val plate = repoFile("$main/ui/screens/EntitiesPlate.kt").readText()
        // Read-only: no write, no Forget/Erase/Pin control, no other route.
        for (banned in listOf("forgetAutoFact", "eraseFact", "\"/api/", "api.post", "ChatHistory", "/api/graph")) {
            assertFalse("the People and things plate must not use $banned", plate.contains(banned))
        }
        assertTrue(plate.contains("JarvisRuntime.memoryUsed("))
        assertTrue(plate.contains("HiddenSection(Entities.TITLE"))
        val brain = repoFile("$main/ui/screens/BrainScreen.kt").readText()
        assertTrue(brain.contains("item(key = \"people-and-things\")"))
        assertTrue(brain.indexOf("item(key = \"topics\")") < brain.indexOf("item(key = \"people-and-things\")"))
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
