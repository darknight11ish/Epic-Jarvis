package com.jarvis.client

import com.jarvis.client.net.ApiError
import com.jarvis.client.net.BrowserEngine
import com.jarvis.client.net.DesktopWrite
import com.jarvis.client.net.JarvisJson
import kotlinx.serialization.json.JsonNull
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.booleanOrNull
import kotlinx.serialization.json.jsonArray
import kotlinx.serialization.json.jsonObject
import kotlinx.serialization.json.jsonPrimitive
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test

/**
 * The headless browser (Obscura) setting on the phone (the owner's decision of
 * 2026-09-29; docs/JARVIS-API.md section 97), held to the table both apps share
 * (`src/test/resources/contract/browser-engine-cases.json`, written by
 * tools/gen_browser_cases.py from backend/jarvis_browser_engine.py; the
 * desktop's tests/browser-engine.mjs runs the same file through
 * browser-engine-rules.js).
 */
class BrowserEngineTest {

    private val table: JsonObject = run {
        val text = requireNotNull(javaClass.classLoader?.getResource("contract/browser-engine-cases.json")) {
            "contract/browser-engine-cases.json is missing - run python3 tools/gen_browser_cases.py"
        }.readText()
        JarvisJson.parseToJsonElement(text) as JsonObject
    }
    private val words: JsonObject = table["words"]!!.jsonObject

    private fun w(key: String): String = words[key]!!.jsonPrimitive.content

    @Test
    fun `the fixed words are the PC's`() {
        assertEquals(w("title"), BrowserEngine.TITLE)
        assertEquals(w("detail"), BrowserEngine.DETAIL)
        assertEquals(w("switch"), BrowserEngine.SWITCH)
        assertEquals(w("mode_title"), BrowserEngine.MODE_TITLE)
        assertEquals(w("stealth"), BrowserEngine.STEALTH)
        assertEquals(w("off_line"), BrowserEngine.OFF_LINE)
        assertEquals(w("waiting_line"), BrowserEngine.WAITING_LINE)
        assertEquals(w("unread"), BrowserEngine.UNREAD)
        assertEquals(w("missing"), BrowserEngine.MISSING)
        assertEquals(w("steps_title"), BrowserEngine.STEPS_TITLE)
        assertEquals(w("steps_note"), BrowserEngine.STEPS_NOTE)
        val modes = table["modes"]!!.jsonArray.map { it.jsonPrimitive.content }
        assertEquals(modes, BrowserEngine.MODES)
        assertEquals(table["default_mode"]!!.jsonPrimitive.content, BrowserEngine.DEFAULT_MODE)
        val labels = words["modes"]!!.jsonObject
        val help = words["mode_help"]!!.jsonObject
        for (id in modes) {
            assertEquals(id, labels[id]!!.jsonPrimitive.content, BrowserEngine.MODE_LABELS[id])
            assertEquals(id, help[id]!!.jsonPrimitive.content, BrowserEngine.MODE_HELP[id])
        }
    }

    @Test
    fun `every settings case is what the PC says`() {
        val cases = table["panels"]!!.jsonArray.map { it.jsonObject }
        assertTrue("no cases found", cases.isNotEmpty())
        for (c in cases) {
            val name = c["name"]!!.jsonPrimitive.content
            val payload = c["payload"]
            val got = BrowserEngine.panel(payload as? JsonObject)
            val want = c["want"]!!.jsonObject
            assertEquals(name, want["available"]!!.jsonPrimitive.booleanOrNull, got.available)
            assertEquals(name, want["obscura"]!!.jsonPrimitive.booleanOrNull, got.obscura)
            assertEquals(name, want["waiting"]!!.jsonPrimitive.booleanOrNull, got.waiting)
            assertEquals(name, want["checked"]!!.jsonPrimitive.booleanOrNull, got.checked)
            assertEquals(name, want["mode"]!!.jsonPrimitive.content, got.mode)
            assertEquals(name, want["line"]!!.jsonPrimitive.content, got.line)
            assertEquals(name, want["status"]!!.jsonPrimitive.content, got.status)
            assertEquals(name, want["install_line"]!!.jsonPrimitive.content, got.installLine)
        }
    }

    @Test
    fun `an answer that is not a status is unavailable, never on`() {
        val p = BrowserEngine.panel(null)
        assertFalse(p.available)
        assertFalse(p.checked)
        assertEquals(BrowserEngine.UNREAD, p.line)
        // "true" written as a string is not a switch position.
        val odd = BrowserEngine.panel(JsonObject(mapOf("obscura" to JsonPrimitive("true"))))
        assertFalse(odd.available)
        assertFalse(odd.obscura)
        val nul = BrowserEngine.panel(JsonObject(mapOf("obscura" to JsonNull)))
        assertFalse(nul.available)
    }

    @Test
    fun `a waiting card shows the switch on but never says it is on`() {
        val p = BrowserEngine.panel(
            JsonObject(mapOf("obscura" to JsonPrimitive(false), "waiting" to JsonPrimitive(true))),
        )
        assertTrue(p.checked)
        assertFalse(p.obscura)
        assertTrue(p.waiting)
        assertEquals(BrowserEngine.WAITING_LINE, p.line)
        val already = BrowserEngine.panel(
            JsonObject(mapOf("obscura" to JsonPrimitive(true), "waiting" to JsonPrimitive(true))),
        )
        assertFalse("already on: nothing is waiting", already.waiting)
    }

    @Test
    fun `the requests carry only a switch position or one of the three modes`() {
        assertEquals("{\"obscura\":true}", BrowserEngine.enabledBody(true))
        assertEquals("{\"obscura\":false}", BrowserEngine.enabledBody(false))
        assertEquals("{\"mode\":\"headless\"}", BrowserEngine.modeBody("headless"))
        assertEquals("{\"mode\":\"auto\"}", BrowserEngine.modeBody("auto"))
        for (bad in listOf("", "Auto", "stealth", "headless ", "proxy", "auto\",\"obscura\":true")) {
            assertNull(bad, BrowserEngine.modeBody(bad))
        }
        assertEquals("/api/browser/engine", BrowserEngine.PATH)
        assertEquals("obscura_enable", BrowserEngine.ACTION)
    }

    @Test
    fun `the card and a route this PC does not have`() {
        assertTrue(BrowserEngine.cardWaiting(listOf("read_files", "obscura_enable")))
        assertFalse(BrowserEngine.cardWaiting(listOf("screen_picture_enable", null)))
        assertTrue(BrowserEngine.missing(ApiError.NotFound))
        assertTrue(BrowserEngine.missing(ApiError.NotAvailable))
        assertFalse(BrowserEngine.missing(ApiError.Server(500, "")))
        assertTrue(BrowserEngine.missing(ApiError.Server(501, "")))
    }

    @Test
    fun `what is said after the switch is pressed or a mode picked`() {
        assertTrue(
            BrowserEngine.said(true, DesktopWrite.Outcome.Waiting(null)).startsWith(
                "Waiting for your approval to turn on the headless browser.",
            ),
        )
        assertEquals("Not changed. no", BrowserEngine.said(true, DesktopWrite.Outcome.Refused("no")))
        assertEquals(
            "The headless browser is off. Jarvis uses the visible browser only.",
            BrowserEngine.said(false, DesktopWrite.Outcome.Done(null)),
        )
        assertEquals("Turned off.", BrowserEngine.said(false, DesktopWrite.Outcome.Done("Turned off.")))
        assertEquals("Saved.", BrowserEngine.saidMode(DesktopWrite.Outcome.Done(null)))
        assertEquals("Not changed. no", BrowserEngine.saidMode(DesktopWrite.Outcome.Refused("no")))
    }

    @Test
    fun `the words are honest about stealth and never offer a proxy`() {
        val s = BrowserEngine.STEALTH
        assertTrue(s.contains("always on"))
        assertTrue(s.contains("ordinary Chrome"))
        assertTrue(s.contains("does not solve captchas"))
        assertTrue(s.contains("block or ban"))
        assertTrue(s.contains("account closed"))
        assertTrue(s.contains("never signs in"))
        assertTrue(BrowserEngine.DETAIL.contains("uses no proxy"))
        assertTrue(BrowserEngine.DETAIL.contains("Off by default"))
        assertTrue(BrowserEngine.STEPS_NOTE.contains("never downloads it by itself"))
        val all = listOf(
            BrowserEngine.TITLE, BrowserEngine.SWITCH, BrowserEngine.MODE_TITLE, BrowserEngine.OFF_LINE,
            BrowserEngine.WAITING_LINE,
        ).joinToString(" ").lowercase()
        assertFalse(all.contains("proxy"))
    }
}
