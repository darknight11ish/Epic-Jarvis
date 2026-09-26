package com.jarvis.client

import com.jarvis.client.net.ApiError
import com.jarvis.client.net.JarvisJson
import com.jarvis.client.net.Reach
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.buildJsonObject
import kotlinx.serialization.json.int
import kotlinx.serialization.json.jsonArray
import kotlinx.serialization.json.jsonObject
import kotlinx.serialization.json.jsonPrimitive
import kotlinx.serialization.json.put
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test

/**
 * Mind's "What Jarvis can reach", read from what the PC REALLY answers.
 *
 * `contract/reach-cases.json` is the real `GET /api/reach` answer
 * (jarvis_reach.view()), written by tools/gen_reach_cases.py - byte for
 * byte the file the desktop builds against.
 */
class ReachTest {

    private val doc: JsonObject = run {
        val text = requireNotNull(javaClass.classLoader?.getResource("contract/reach-cases.json")) {
            "contract/reach-cases.json is missing - run tools/gen_reach_cases.py"
        }.readText()
        JarvisJson.parseToJsonElement(text) as JsonObject
    }
    private val cases = doc["cases"]!!.jsonObject
    private val ids = doc["ids"]!!.jsonArray.map { it.jsonPrimitive.content }

    private fun view(case: String): Reach.View =
        requireNotNull(Reach.parse(cases[case]!!.jsonObject)) { "$case did not parse" }

    @Test
    fun `the words for the screen are the PC's own`() {
        assertEquals(doc["title"]!!.jsonPrimitive.content, Reach.TITLE)
        assertEquals(doc["detail"]!!.jsonPrimitive.content, Reach.DETAIL)
        assertEquals(doc["missing"]!!.jsonPrimitive.content, Reach.MISSING)
        assertEquals(doc["tools_title"]!!.jsonPrimitive.content, Reach.TOOLS_TITLE)
        assertEquals(doc["tools_none"]!!.jsonPrimitive.content, Reach.TOOLS_NONE)
        assertEquals(doc["everything_else"]!!.jsonPrimitive.content, Reach.EVERYTHING_ELSE)
    }

    @Test
    fun `every real view is read, every row in the PC's order`() {
        assertTrue(cases.keys.size >= 4)
        for (name in cases.keys) {
            val v = view(name)
            assertEquals(name, ids, v.rows.map { it.id })
            assertEquals(name, cases[name]!!.jsonObject["on"]!!.jsonPrimitive.int, v.on)
            val tools = cases[name]!!.jsonObject["tools"]!!.jsonArray.map { it.jsonObject["id"]!!.jsonPrimitive.content }
            assertEquals(name, tools, v.tools.map { it.id })
        }
        assertEquals(0, view("nothing_set_up").on)
        assertTrue(view("nothing_set_up").tools.isEmpty())
        val all = view("everything_on")
        val web = all.rows.first { it.id == "web_search" }
        assertEquals(
            listOf("Goes to: ${web.where}", "Asks you first: ${web.asks}", web.line),
            Reach.lines(web, all),
        )
        assertEquals("Web search - On", Reach.heading(web))
        // Sending email is a real row since 2026-09-25: on once reading is
        // set up, and it always asks.
        val send = all.rows.first { it.id == "email_send" }
        assertTrue(send.on)
        assertEquals("Yes, every time", send.asks)
        assertEquals(
            listOf("Goes to: ${send.where}", "Asks you first: ${send.asks}", send.line),
            Reach.lines(send, all),
        )
        val blocked = view("blocked_and_no_key").rows.first { it.id == "email_read" }
        assertEquals("blocked", blocked.state)
        assertFalse(blocked.on)
    }

    @Test
    fun `an older PC says so`() {
        assertNull(Reach.parse(buildJsonObject { put("available", false) }))
        assertNull(Reach.parse(buildJsonObject { put("error", "nope") }))
        assertTrue(Reach.missing(ApiError.NotFound))
        assertTrue(Reach.missing(ApiError.NotAvailable))
        assertFalse(Reach.missing(ApiError.BadToken))
    }
}
