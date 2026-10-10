package com.jarvis.client

import com.jarvis.client.net.HandoffFront
import com.jarvis.client.net.JarvisJson
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.boolean
import kotlinx.serialization.json.jsonArray
import kotlinx.serialization.json.jsonObject
import kotlinx.serialization.json.jsonPrimitive
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

/**
 * What a captcha does about the browser window it is blocking, read from what
 * the PC REALLY answers ([HandoffFront], backend/jarvis_handoff_front.py; the
 * owner's decision of 2026-10-09: "1 by default with the option for 2 in the
 * settings of Jarvis").
 *
 * `contract/handoff-cases.json` is written by tools/gen_handoff_cases.py from
 * the real modules - byte for byte the file the desktop builds against. Its
 * `front_words` are the PC's own sentences, which this phone must say word for
 * word, and its `front_*` values are the two choices and the default, read from
 * the same file, so neither app can drift.
 */
class HandoffFrontTest {

    private val doc: JsonObject = run {
        val text = requireNotNull(javaClass.classLoader?.getResource("contract/handoff-cases.json")) {
            "contract/handoff-cases.json is missing - run tools/gen_handoff_cases.py"
        }.readText()
        JarvisJson.parseToJsonElement(text) as JsonObject
    }

    private fun obj(case: String): JsonObject = doc[case]!!.jsonObject

    private val view: JsonObject = obj("front_route_get")["body"]!!.jsonObject

    @Test
    fun `the two choices and the default are the PC's own`() {
        assertEquals(
            doc["front_modes"]!!.jsonArray.map { it.jsonPrimitive.content },
            HandoffFront.MODES,
        )
        assertEquals(doc["front_default"]!!.jsonPrimitive.content, HandoffFront.DEFAULT)
        assertEquals(HandoffFront.DEFAULT, HandoffFront.LEAVE_IN_PLACE)
        assertEquals(doc["front_looser"]!!.jsonPrimitive.content, HandoffFront.BRING_TO_FRONT)
        assertEquals(2, HandoffFront.MODES.size)
    }

    @Test
    fun `every word is the PC's own, word for word`() {
        val words = obj("front_words")
        assertEquals(words.keys, HandoffFront.WORDS.keys)
        for ((key, sentence) in HandoffFront.WORDS) {
            assertEquals(key, words[key]!!.jsonPrimitive.content, sentence)
        }
        assertEquals(HandoffFront.TITLE, words["title"]!!.jsonPrimitive.content)
        // The two choice labels and their lines come from the PC's own table,
        // not from a second copy here.
        for (id in HandoffFront.MODES) {
            assertEquals(words[id]!!.jsonPrimitive.content, HandoffFront.LABELS[id])
            assertEquals(words["${id}_detail"]!!.jsonPrimitive.content, HandoffFront.HELP[id])
        }
    }

    @Test
    fun `the route is the PC's, and never one of the hand-off's own`() {
        assertEquals(doc["routes"]!!.jsonObject["front"]!!.jsonPrimitive.content, HandoffFront.PATH)
        assertEquals("/api/chatbot/handoff_front", HandoffFront.PATH)
        assertFalse(HandoffFront.PATH.startsWith("/api/chatbot/handoff/"))
    }

    @Test
    fun `the card is raised under the PC's own action, which is decided on the PC`() {
        assertEquals("handoff_bring_to_front", HandoffFront.ACTION)
        assertEquals(true, view["pc_only"]!!.jsonPrimitive.boolean)
    }

    @Test
    fun `the default view touches no window and raises nothing`() {
        val v = HandoffFront.view(view)
        assertTrue(v.available)
        assertEquals(HandoffFront.LEAVE_IN_PLACE, v.mode)
        assertFalse(v.raises)
        assertFalse(v.waiting)
        assertEquals(HandoffFront.WORDS["leave_in_place_detail"], v.line)
        // The PC's own answers for the same three moments.
        assertFalse(doc["front_stuck_default"]!!.jsonPrimitive.boolean)
        assertTrue(doc["front_stuck_chosen"]!!.jsonPrimitive.boolean)
        assertFalse(doc["front_active_chosen"]!!.jsonPrimitive.boolean)
        assertFalse(doc["front_nothing_waiting_chosen"]!!.jsonPrimitive.boolean)
    }

    @Test
    fun `choosing to bring the window forward is what raises it`() {
        val chosen = JsonObject(view + ("mode" to kotlinx.serialization.json.JsonPrimitive("bring_to_front")))
        val v = HandoffFront.view(chosen)
        assertEquals(HandoffFront.BRING_TO_FRONT, v.mode)
        assertTrue(v.raises)
        assertEquals(HandoffFront.WORDS["bring_to_front_detail"], v.line)
        assertTrue(v.line.contains("screen"))
        assertTrue(v.line.contains("keyboard"))
        assertTrue(v.line.contains("asks for your approval"))
    }

    @Test
    fun `a damaged file reads as the default, never as bringing the window forward`() {
        val damaged = JsonObject(
            view + ("why" to kotlinx.serialization.json.JsonPrimitive(HandoffFront.DAMAGED)),
        )
        val v = HandoffFront.view(damaged)
        assertEquals(HandoffFront.DEFAULT, v.mode)
        assertFalse(v.raises)
        assertEquals(HandoffFront.DAMAGED, v.line)
        assertEquals(HandoffFront.DAMAGED, v.why)
    }

    @Test
    fun `anything not the PC's exact shape is 'could not read it', never a guess`() {
        for (bad in listOf(null, JsonObject(emptyMap()))) {
            val v = HandoffFront.view(bad)
            assertFalse(v.available)
            assertEquals(HandoffFront.DEFAULT, v.mode)
            assertFalse(v.raises)
            assertEquals(HandoffFront.UNREAD, v.line)
        }
        for (mode in listOf("forever", "BRING_TO_FRONT", "bring_to_front today")) {
            val v = HandoffFront.view(
                JsonObject(view + ("mode" to kotlinx.serialization.json.JsonPrimitive(mode))),
            )
            assertFalse(mode, v.available)
            assertEquals(HandoffFront.DEFAULT, v.mode)
        }
    }

    @Test
    fun `a card waiting is said plainly, and nothing has changed yet`() {
        val waiting = JsonObject(
            view + ("waiting" to kotlinx.serialization.json.JsonPrimitive(true)),
        )
        val v = HandoffFront.view(waiting)
        assertTrue(v.waiting)
        assertEquals(HandoffFront.WAITING_LINE, v.line)
        assertEquals(HandoffFront.DEFAULT, v.mode)
    }

    @Test
    fun `how the last card ended rides along in the PC's own words`() {
        val last = JsonObject(
            view + ("last" to JsonObject(mapOf(
                "message" to kotlinx.serialization.json.JsonPrimitive(HandoffFront.OFF_NOW),
            ))),
        )
        assertEquals(HandoffFront.OFF_NOW, HandoffFront.view(last).lastWords)
        assertEquals("", HandoffFront.view(view).lastWords)
    }

    @Test
    fun `the body carries one of the two names and nothing else`() {
        assertEquals("{\"mode\":\"leave_in_place\"}", HandoffFront.body(HandoffFront.LEAVE_IN_PLACE))
        assertEquals("{\"mode\":\"bring_to_front\"}", HandoffFront.body(HandoffFront.BRING_TO_FRONT))
        for (bad in listOf("", "on", "off", "raise", "front", "LEAVE_IN_PLACE",
                           "leave_in_place ")) {
            assertEquals(bad, null, HandoffFront.body(bad))
        }
    }
}
