package com.jarvis.client

import com.jarvis.client.net.JarvisJson
import com.jarvis.client.net.ScreenRules
import kotlinx.serialization.json.JsonNull
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.booleanOrNull
import kotlinx.serialization.json.intOrNull
import kotlinx.serialization.json.jsonArray
import kotlinx.serialization.json.jsonObject
import kotlinx.serialization.json.jsonPrimitive
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test

/**
 * "Look at this" and "Watch with me" on the phone, held to the table both
 * apps share (`src/test/resources/contract/screen-cases.json`, written by
 * tools/gen_screen_cases.py from backend/jarvis_screen.py; the desktop's
 * tests/look-rules.mjs runs the same file through look-rules.js).
 */
class ScreenRulesTest {

    private val table: JsonObject = run {
        val text = requireNotNull(javaClass.classLoader?.getResource("contract/screen-cases.json")) {
            "contract/screen-cases.json is missing - run python3 tools/gen_screen_cases.py"
        }.readText()
        JarvisJson.parseToJsonElement(text) as JsonObject
    }

    private val statuses: JsonObject = table["statuses"]!!.jsonObject

    private fun status(name: String?): JsonObject? = name?.let { statuses[it] as? JsonObject }

    private fun cases(key: String): List<JsonObject> = table[key]!!.jsonArray.map { it.jsonObject }

    private fun JsonObject.s(key: String): String = this[key]!!.jsonPrimitive.content

    private fun JsonObject.b(key: String): Boolean =
        (this[key] as? JsonPrimitive)?.booleanOrNull ?: false

    private fun optStr(o: JsonObject, key: String): String? =
        (o[key] as? JsonPrimitive)?.takeIf { it.isString }?.content

    private fun optInt(o: JsonObject, key: String): Int? = (o[key] as? JsonPrimitive)?.intOrNull

    @Test
    fun `the fixed words are the PC's`() {
        val seen = table["words"]!!.jsonObject["seen"]!!.jsonObject
        assertEquals(seen.s("title"), ScreenRules.TITLE)
        assertEquals(seen.s("paused_title"), ScreenRules.PAUSED_TITLE)
        assertEquals(seen.s("ended_title"), ScreenRules.ENDED_TITLE)
        assertEquals(seen.s("stop"), ScreenRules.STOP)
        assertEquals(seen.s("more"), ScreenRules.MORE)
        assertEquals(seen.s("drop"), ScreenRules.DROP)
        for ((k, v) in seen) assertEquals(k, v.jsonPrimitive.content, ScreenRules.SEEN[k])
        val words = table["words"]!!.jsonObject
        assertEquals(words.s("dot"), ScreenRules.DOT)
        assertEquals(words["ended_show_s"]!!.jsonPrimitive.intOrNull, ScreenRules.ENDED_SHOW_S)
        assertTrue(words["marks"]!!.jsonArray.map { it.jsonPrimitive.content }.contains(ScreenRules.MARK))
    }

    @Test
    fun `the sign, every case`() {
        val all = cases("sign")
        assertTrue("only ${all.size} cases", all.size >= 15)
        for (c in all) {
            val w = c["want"]!!.jsonObject
            val want = ScreenRules.Sign(
                show = w.b("show"), on = w.b("on"), title = w.s("title"), detail = w.s("detail"),
                stop = w.s("stop"), more = w.s("more"), tone = w.s("tone"),
            )
            val got = ScreenRules.sign(
                status(optStr(c, "status")), stale = c.b("stale"), endedAgo = optInt(c, "ended_ago"),
            )
            assertEquals(c.s("name"), want, got)
        }
    }

    @Test
    fun `the line after a look, every case`() {
        for (c in cases("look_line")) {
            val payload = c["payload"] as? JsonObject
            val w = c["want"]!!.jsonObject
            assertEquals(c.s("name"), ScreenRules.Line(w.s("text"), w.s("tone")), ScreenRules.lookLine(payload))
        }
    }

    @Test
    fun `the mark on a question, every case`() {
        for (c in cases("mark")) {
            assertEquals(c.s("name"), c.s("want"), ScreenRules.screenMark(status(optStr(c, "status"))))
        }
        assertEquals("", ScreenRules.screenMark(null))
        assertEquals("", ScreenRules.screenMark(JsonObject(mapOf("look_held" to JsonNull))))
    }

    @Test
    fun `minutes left`() {
        assertEquals("24 min left", ScreenRules.minutesLeft(1440.0))
        assertEquals("1 min left", ScreenRules.minutesLeft(60.0))
        assertEquals("2 min left", ScreenRules.minutesLeft(61.0))
        assertEquals("under a minute left", ScreenRules.minutesLeft(45.0))
        assertEquals("", ScreenRules.minutesLeft(-1.0))
        assertEquals("", ScreenRules.minutesLeft(null))
    }

    @Test
    fun `a status is only ever read for its fixed keys`() {
        val keys = table["words"]!!.jsonObject["status_keys"]!!.jsonArray.map { it.jsonPrimitive.content }.toSet()
        for ((name, st) in statuses) assertEquals(name, keys, (st as JsonObject).keys)
        // A wrong answer that carries the screen's words is never shown.
        val leaked = ScreenRules.lookLine(
            JsonObject(mapOf("ok" to JsonPrimitive(false), "part" to JsonPrimitive("Snorvelquist balance owed"))),
        )
        assertTrue(!leaked.text.contains("Snorvelquist"))
    }
}
