package com.jarvis.client

import com.jarvis.client.net.ChatTags
import com.jarvis.client.net.Topics
import kotlinx.serialization.json.Json
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.int
import kotlinx.serialization.json.jsonArray
import kotlinx.serialization.json.jsonObject
import kotlinx.serialization.json.jsonPrimitive
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test

/**
 * Topics share the chat tags' eight colours and icon drawings (docs/
 * TOPIC-CONTROLS-DESIGN.md section 2): the fixture's palette must be the one
 * [ChatTags] draws, and its ready-made topics must use only colours and icons
 * the phone can draw. Kept apart from TopicsTest because it needs ChatTags
 * (which reads ChatLog); TopicsTest itself is plain JVM with no other file.
 */
class TopicsLookTest {

    private val doc: JsonObject = run {
        val text = requireNotNull(javaClass.classLoader?.getResource("contract/topics-cases.json")) {
            "contract/topics-cases.json is missing - run tools/gen_topics_cases.py"
        }.readText()
        Json.parseToJsonElement(text) as JsonObject
    }

    private fun hex(s: String): Int = s.removePrefix("#").toInt(16)

    @Test
    fun `the fixture's palette is the chat tags' palette`() {
        val palette = doc["palette"]!!.jsonArray.map { it.jsonObject }
        assertEquals(ChatTags.COLOUR_NAMES, palette.map { it["name"]!!.jsonPrimitive.content })
        assertEquals(ChatTags.INK_LIGHT, palette.map { hex(it["light"]!!.jsonPrimitive.content) })
        assertEquals(ChatTags.INK_DARK, palette.map { hex(it["dark"]!!.jsonPrimitive.content) })
        assertEquals(Topics.COLOURS, ChatTags.COLOUR_NAMES.size)
    }

    @Test
    fun `the ready-made topics and Unsorted use slots and icons that exist`() {
        val starters = doc["starters"]!!.jsonArray.map { it.jsonObject } + doc["unsorted"]!!.jsonObject
        for (s in starters) {
            val colour = s["colour"]!!.jsonPrimitive.int
            assertTrue("colour $colour", colour in ChatTags.COLOUR_NAMES.indices)
            assertEquals(colour, Topics.slot(colour))
            assertTrue(s["icon"]!!.jsonPrimitive.content in Topics.ICONS)
        }
    }

    @Test
    fun `the topics icons are the tags' ten plus heart, coin and people`() {
        assertEquals(ChatTags.ICONS + listOf("heart", "coin", "people"), Topics.ICONS)
    }

    @Test
    fun `a colour slot out of range reads as slate`() {
        assertEquals(6, Topics.slot(-1))
        assertEquals(6, Topics.slot(8))
    }
}
