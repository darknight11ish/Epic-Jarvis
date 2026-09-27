package com.jarvis.client

import com.jarvis.client.net.JarvisJson
import com.jarvis.client.voice.PrivateAloud
import kotlinx.serialization.json.JsonNull
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.boolean
import kotlinx.serialization.json.jsonArray
import kotlinx.serialization.json.jsonObject
import kotlinx.serialization.json.jsonPrimitive
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test

/**
 * One table for both apps: may the answer to a VOICE question be read
 * aloud? Held to `src/test/resources/contract/private-aloud-cases.json`,
 * which tools/gen_private_aloud_cases.py writes; the desktop's
 * tests/private-speech.mjs runs the same file through private-speech.js.
 * The owner's decision of 2026-09-27: answers from web search and home
 * status (weather included) are read aloud; email, calendar, notes, memory
 * and any unknown tool stay on screen - and every earlier step of the rule
 * keeps its priority.
 */
class PrivateAloudContractTest {

    private val table: JsonObject = run {
        val text = requireNotNull(javaClass.classLoader?.getResource("contract/private-aloud-cases.json")) {
            "contract/private-aloud-cases.json is missing - run python3 tools/gen_private_aloud_cases.py"
        }.readText()
        JarvisJson.parseToJsonElement(text) as JsonObject
    }

    @Test
    fun `the read-aloud list and the fixed line are the table's`() {
        val tools = table["read_aloud_tools"]!!.jsonArray.map { it.jsonPrimitive.content }.toSet()
        assertEquals(tools, PrivateAloud.READ_ALOUD_TOOLS)
        assertEquals(table["on_screen"]!!.jsonPrimitive.content, PrivateAloud.ON_SCREEN)
    }

    @Test
    fun `every case in the table, through the phone's own code`() {
        val cases = table["cases"]!!.jsonArray
        assertTrue("only ${cases.size} cases", cases.size > 40)
        for (element in cases) {
            val c = element.jsonObject
            val name = c["name"]!!.jsonPrimitive.content
            val heard = c["heard"]!!.jsonObject
            fun flag(key: String): Boolean = heard[key]!!.jsonPrimitive.boolean
            val routeJson = c["route"]
            val header: String? = if (routeJson == null || routeJson is JsonNull) null else routeJson.toString()
            val steps = c["steps"]!!.jsonArray
            val stream = c["stream"]!!.jsonPrimitive.content
            val runs = steps.count { PrivateAloud.isToolRun(it) }.toLong()
            val privateRuns = steps.count { PrivateAloud.isPrivateToolRun(it) }.toLong()
            val start = PrivateAloud.Watch(runs = 0L, drops = 0L, live = stream != "stale_at_start", privateRuns = 0L)
            val now = PrivateAloud.Watch(
                runs = runs,
                drops = if (stream == "dropped") 1L else 0L,
                live = stream != "stale_now",
                privateRuns = privateRuns,
            )
            val got = PrivateAloud.mayRead(
                privateAloud = flag("private_aloud"),
                questionPrivate = flag("question_private"),
                route = PrivateAloud.route(header),
                toolRan = PrivateAloud.toolRan(start, now),
                toolsKnown = PrivateAloud.toolsKnown(start, now),
                memoryAloud = flag("memory_aloud"),
                sensitiveAloud = flag("sensitive_aloud"),
            )
            assertEquals(name, c["read"]!!.jsonPrimitive.boolean, got)
        }
    }
}
