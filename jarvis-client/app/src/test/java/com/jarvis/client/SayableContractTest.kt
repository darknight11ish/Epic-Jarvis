package com.jarvis.client

import com.jarvis.client.net.JarvisJson
import com.jarvis.client.net.Sayable
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.jsonArray
import kotlinx.serialization.json.jsonPrimitive
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test

/**
 * "Things you can say" - held to `src/test/resources/contract/sayable-cases.json`,
 * which tools/gen_sayable_cases.py makes from backend/jarvis_sayable.py. The
 * desktop's tests/sayable.mjs reads the same file, so the two apps cannot
 * carry a different list.
 */
class SayableContractTest {

    private val cases: JsonObject = run {
        val text = requireNotNull(javaClass.classLoader?.getResource("contract/sayable-cases.json")) {
            "contract/sayable-cases.json is missing - run python3 tools/gen_sayable_cases.py"
        }.readText()
        JarvisJson.parseToJsonElement(text) as JsonObject
    }

    private fun text(key: String) = cases[key]!!.jsonPrimitive.content
    private fun list(key: String) = cases[key]!!.jsonArray.map { it.jsonPrimitive.content }

    @Test
    fun `the title, detail and footer are the backend's own words`() {
        assertEquals(text("title"), Sayable.TITLE)
        assertEquals(text("detail"), Sayable.DETAIL)
        assertEquals(text("footer"), Sayable.FOOTER)
    }

    @Test
    fun `SENTENCES is the backend's list, in the same order`() {
        assertEquals(list("sentences"), Sayable.SENTENCES)
        assertTrue("${Sayable.SENTENCES.size} sentences", Sayable.SENTENCES.size in 5..8)
    }

    @Test
    fun `WALKTHROUGH_EXAMPLES is exactly the backend's 3, a subset of SENTENCES`() {
        val examples = list("walkthrough_examples")
        assertEquals(examples, Sayable.WALKTHROUGH_EXAMPLES)
        assertEquals(3, Sayable.WALKTHROUGH_EXAMPLES.size)
        for (s in Sayable.WALKTHROUGH_EXAMPLES) {
            assertTrue(s, Sayable.SENTENCES.contains(s))
        }
    }

    @Test
    fun `the Help answer is the backend's words and names every sentence`() {
        assertEquals(text("help_title"), Sayable.HELP_TITLE)
        assertEquals(text("help_body"), Sayable.HELP_BODY)
        for (s in Sayable.SENTENCES) {
            assertTrue("Help is missing $s", Sayable.HELP_BODY.contains(s))
        }
        assertTrue(Sayable.HELP_BODY.contains("what can you do?"))
    }

    @Test
    fun `no duplicate sentence, no blank one`() {
        assertEquals(Sayable.SENTENCES.size, Sayable.SENTENCES.toSet().size)
        for (s in Sayable.SENTENCES) assertTrue(s.isNotBlank())
    }
}
