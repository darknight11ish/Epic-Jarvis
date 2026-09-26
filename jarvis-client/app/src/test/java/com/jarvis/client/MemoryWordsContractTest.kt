package com.jarvis.client

import com.jarvis.client.net.AutoLearn
import com.jarvis.client.net.JarvisJson
import com.jarvis.client.net.MemoryAsOf
import com.jarvis.client.net.MemoryCards
import com.jarvis.client.net.MemoryCounts
import com.jarvis.client.net.MemoryWords
import kotlinx.serialization.json.JsonElement
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.jsonArray
import kotlinx.serialization.json.jsonObject
import kotlinx.serialization.json.jsonPrimitive
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test
import java.time.LocalDate
import java.time.ZoneOffset

/**
 * The memory words both apps use (the memory review of 2026-09-27, I8-I11),
 * held to `src/test/resources/contract/memory-words-cases.json`, which
 * tools/gen_memory_words_cases.py makes from the real backend. The desktop's
 * tests/memory-words.mjs reads the same file, so the two apps cannot word
 * memory differently.
 */
class MemoryWordsContractTest {

    private val cases: JsonObject = run {
        val text = requireNotNull(javaClass.classLoader?.getResource("contract/memory-words-cases.json")) {
            "contract/memory-words-cases.json is missing - run python3 tools/gen_memory_words_cases.py"
        }.readText()
        JarvisJson.parseToJsonElement(text) as JsonObject
    }

    /** A string, or null for JSON null / anything else. */
    private fun JsonElement?.text(): String? = (this as? JsonPrimitive)?.takeIf { it.isString }?.content

    @Test
    fun `the words are the fixture's, word for word`() {
        val words = cases["words"]!!.jsonObject.mapValues { it.value.jsonPrimitive.content }
        assertEquals(words, MemoryWords.WORDS)
        assertEquals(cases["months"]!!.jsonArray.map { it.jsonPrimitive.content }, MemoryWords.MONTHS)
        // The past-date tags and the card's reason prefix are these words.
        assertEquals(words["true_then"], MemoryAsOf.TRUE_THEN)
        assertEquals(words["no_longer_true"], MemoryAsOf.NO_LONGER_TRUE)
        assertEquals(words["reason_prefix"], MemoryCards.AUTO_REASON_PREFIX)
    }

    @Test
    fun `plain dates - 1 January 2026, and nothing for a day that is not real`() {
        for (c in cases["dates"]!!.jsonArray) {
            val iso = c.jsonObject["iso"].text()
            assertEquals(iso, c.jsonObject["says"].text(), MemoryWords.plainDate(iso))
        }
    }

    @Test
    fun `I10 - a Saved automatically row's true_from is shown as true from 1 January 2026`() {
        val zone = ZoneOffset.UTC
        val today = LocalDate.of(2026, 9, 27)
        for (c in cases["true_from"]!!.jsonArray) {
            val row = c.jsonObject["row"]!!.jsonObject
            val want = c.jsonObject["line"].text()
            val fact = AutoLearn.page(JsonObject(mapOf("facts" to kotlinx.serialization.json.JsonArray(listOf(row)))))
                .facts.single()
            assertEquals(row.toString(), want, MemoryWords.trueFromLine(fact.trueFrom))
            val line = AutoLearn.rowLine(fact, zone, today)
            if (want != null) {
                assertTrue(line, line.endsWith(want))
            } else {
                assertFalse(line, line.contains(MemoryWords.TRUE_FROM))
            }
        }
    }

    @Test
    fun `I8 - the memory counts' rows, from the real status in every re-ranker state`() {
        for (c in cases["status"]!!.jsonArray) {
            val o = c.jsonObject
            val want = o["rows"]!!.jsonArray.map { r ->
                val pair = r.jsonArray
                pair[0].jsonPrimitive.content to pair[1].jsonPrimitive.content
            }
            assertEquals(o["name"].text(), want, MemoryCounts.fields(o["status"]!!.jsonObject))
        }
    }

    @Test
    fun `I9 - the reason line, and the older-news warning on its own line`() {
        for (c in cases["cards"]!!.jsonArray) {
            val o = c.jsonObject
            val row = o["row"]!!.jsonObject
            val reason = o["reason"].text()
            val older = o["older"].text()
            assertEquals(row.toString(), MemoryWords.CardLines(reason, older), MemoryWords.cardLines(row))
            val card = MemoryCards.from(row)
            assertEquals(row.toString(), reason, card.autoReasonLine)
            assertEquals(row.toString(), older, card.olderNewsLine)
        }
    }

    @Test
    fun `the repeats note carries the desktop's label`() {
        val notes = MemoryCards.setupNotes(
            JarvisJson.parseToJsonElement("""{"setup": {"near_duplicates_note": "2 proposal(s) said the same."}}""")
                .jsonObject,
        )
        assertEquals(listOf("${cases["words"]!!.jsonObject["repeats"].text()}: 2 proposal(s) said the same."), notes)
    }
}
