package com.jarvis.client

import com.jarvis.client.net.JarvisJson
import com.jarvis.client.net.MemoryAsOf
import kotlinx.serialization.json.JsonObject
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Test

/**
 * "What did Jarvis know on this date?" shows the facts, not how many there
 * were (audit K3: the plate said "Facts: 2" and nothing else).
 *
 * The body is the shape `backend/bitemporal.patch` sends for `?known_at=`:
 * every column of the `facts` table (`jarvis_memory.py`'s CREATE TABLE) plus
 * the `current` the handler adds, verdict as of that moment.
 */
class MemoryAsOfTest {

    private fun body(json: String) = JarvisJson.parseToJsonElement(json) as JsonObject

    private val real = body(
        """
        {"available": true,
         "facts": [
           {"id": 3, "text": "The owner lives on Elm Street", "source": "chat",
            "created": 1789000000.0, "valid_from": 1789000000.0, "valid_to": null,
            "retired_at": null, "retired_by": null, "embedded": 1, "meta": null,
            "current": true},
           {"id": 2, "text": "Mario works at Acme", "source": "chat",
            "created": 1788000000.0, "valid_from": 1788000000.0, "valid_to": 1789500000.0,
            "retired_at": 1795000000.0, "retired_by": 4, "embedded": 1, "meta": null,
            "current": false}
         ],
         "known_at": 1790000000.0,
         "note": "what Jarvis believed at that moment, right or wrong. Read-only: you cannot edit the past.",
         "learning": true, "pending": 4}
        """,
    )

    @Test
    fun `each fact is shown by its words, tagged true then or no longer true`() {
        val answer = MemoryAsOf.parse(real)!!
        assertEquals(
            listOf(
                MemoryAsOf.Fact("The owner lives on Elm Street", trueThen = true),
                MemoryAsOf.Fact("Mario works at Acme", trueThen = false),
            ),
            answer.facts,
        )
        assertEquals("true then", MemoryAsOf.tag(answer.facts[0]))
        assertEquals("no longer true", MemoryAsOf.tag(answer.facts[1]))
        assertEquals(
            "what Jarvis believed at that moment, right or wrong. Read-only: you cannot edit the past.",
            answer.note,
        )
    }

    @Test
    fun `nothing known then is an empty list, not a failure`() {
        val empty = MemoryAsOf.parse(body("""{"available": true, "facts": [], "known_at": 1.1e9}"""))!!
        assertEquals(emptyList<MemoryAsOf.Fact>(), empty.facts)
        assertNull(empty.note)
    }

    @Test
    fun `an older backend without current gets no tag, and junk rows are skipped`() {
        val old = MemoryAsOf.parse(
            body("""{"facts": [{"id": 1, "text": "  Old fact  "}, {"id": 2}, "not a row", {"text": ""}]}"""),
        )!!
        assertEquals(listOf(MemoryAsOf.Fact("Old fact", trueThen = null)), old.facts)
        assertNull(MemoryAsOf.tag(old.facts[0]))
    }

    @Test
    fun `no facts list at all is not read as nothing known`() {
        assertNull(MemoryAsOf.parse(body("""{"available": true, "known_at": 1790000000.0}""")))
    }
}
