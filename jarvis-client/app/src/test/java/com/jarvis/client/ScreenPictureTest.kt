package com.jarvis.client

import com.jarvis.client.net.ApiError
import com.jarvis.client.net.DesktopWrite
import com.jarvis.client.net.JarvisJson
import com.jarvis.client.net.ScreenPicture
import kotlinx.serialization.json.JsonNull
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.booleanOrNull
import kotlinx.serialization.json.jsonArray
import kotlinx.serialization.json.jsonObject
import kotlinx.serialization.json.jsonPrimitive
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNotNull
import org.junit.Assert.assertTrue
import org.junit.Test

/**
 * Picture mode on the phone (the owner's decision of 2026-09-29;
 * docs/JARVIS-API.md section 96.1), held to the table both apps share
 * (`src/test/resources/contract/screen-cases.json`, written by
 * tools/gen_screen_cases.py from backend/jarvis_screen_picture.py; the
 * desktop's tests/look-rules.mjs runs the same file through look-rules.js).
 */
class ScreenPictureTest {

    private val table: JsonObject = run {
        val text = requireNotNull(javaClass.classLoader?.getResource("contract/screen-cases.json")) {
            "contract/screen-cases.json is missing - run python3 tools/gen_screen_cases.py"
        }.readText()
        JarvisJson.parseToJsonElement(text) as JsonObject
    }
    private val picture: JsonObject = table["picture"]!!.jsonObject
    private val words: JsonObject = picture["words"]!!.jsonObject

    private fun w(key: String): String = words[key]!!.jsonPrimitive.content

    @Test
    fun `the fixed words are the PC's`() {
        assertEquals(w("title"), ScreenPicture.TITLE)
        assertEquals(w("detail"), ScreenPicture.DETAIL)
        assertEquals(w("switch"), ScreenPicture.SWITCH)
        assertEquals(w("off_line"), ScreenPicture.OFF_LINE)
        assertEquals(w("waiting_line"), ScreenPicture.WAITING_LINE)
        assertEquals(w("unread"), ScreenPicture.UNREAD)
        assertEquals(w("missing"), ScreenPicture.MISSING)
        assertEquals(w("steps_title"), ScreenPicture.STEPS_TITLE)
        assertEquals(w("steps_note"), ScreenPicture.STEPS_NOTE)
    }

    @Test
    fun `every settings case is what the PC says`() {
        val cases = picture["panels"]!!.jsonArray.map { it.jsonObject }
        assertTrue("no cases found", cases.isNotEmpty())
        for (c in cases) {
            val name = c["name"]!!.jsonPrimitive.content
            val payload = c["payload"]
            val got = ScreenPicture.panel(payload as? JsonObject)
            val want = c["want"]!!.jsonObject
            assertEquals(name, want["available"]!!.jsonPrimitive.booleanOrNull, got.available)
            assertEquals(name, want["enabled"]!!.jsonPrimitive.booleanOrNull, got.enabled)
            assertEquals(name, want["waiting"]!!.jsonPrimitive.booleanOrNull, got.waiting)
            assertEquals(name, want["checked"]!!.jsonPrimitive.booleanOrNull, got.checked)
            assertEquals(name, want["line"]!!.jsonPrimitive.content, got.line)
            assertEquals(name, want["measured"]!!.jsonPrimitive.content, got.measured)
            assertEquals(name, want["install_line"]!!.jsonPrimitive.content, got.installLine)
        }
    }

    @Test
    fun `an answer that is not a status is unavailable, never on`() {
        val p = ScreenPicture.panel(null)
        assertFalse(p.available)
        assertFalse(p.checked)
        assertEquals(ScreenPicture.UNREAD, p.line)
        // "true" written as a string is not a switch position.
        val odd = ScreenPicture.panel(JsonObject(mapOf("enabled" to JsonPrimitive("true"))))
        assertFalse(odd.available)
        assertFalse(odd.enabled)
        val nul = ScreenPicture.panel(JsonObject(mapOf("enabled" to JsonNull)))
        assertFalse(nul.available)
    }

    @Test
    fun `a waiting card shows the switch on but never says it is on`() {
        val p = ScreenPicture.panel(
            JsonObject(mapOf("enabled" to JsonPrimitive(false), "waiting" to JsonPrimitive(true))),
        )
        assertTrue(p.checked)
        assertFalse(p.enabled)
        assertTrue(p.waiting)
        assertEquals(ScreenPicture.WAITING_LINE, p.line)
        val already = ScreenPicture.panel(
            JsonObject(mapOf("enabled" to JsonPrimitive(true), "waiting" to JsonPrimitive(true))),
        )
        assertFalse("already on: nothing is waiting", already.waiting)
    }

    @Test
    fun `the request and the card`() {
        assertEquals("{\"enabled\":true}", ScreenPicture.enabledBody(true))
        assertEquals("{\"enabled\":false}", ScreenPicture.enabledBody(false))
        assertEquals("/api/screen/picture", ScreenPicture.PATH)
        assertEquals("screen_picture_enable", ScreenPicture.ACTION)
        assertTrue(ScreenPicture.cardWaiting(listOf("read_files", "screen_picture_enable")))
        assertFalse(ScreenPicture.cardWaiting(listOf("phone_notifications_read", null)))
        assertTrue(ScreenPicture.missing(ApiError.NotFound))
        assertTrue(ScreenPicture.missing(ApiError.NotAvailable))
        assertFalse(ScreenPicture.missing(ApiError.Server(500, "")))
        assertTrue(ScreenPicture.missing(ApiError.Server(501, "")))
    }

    @Test
    fun `what is said after the switch is pressed`() {
        assertTrue(
            ScreenPicture.said(true, DesktopWrite.Outcome.Waiting(null)).startsWith(
                "Waiting for your approval to turn on picture mode.",
            ),
        )
        assertEquals(
            "Not changed. no",
            ScreenPicture.said(true, DesktopWrite.Outcome.Refused("no")),
        )
        assertEquals(
            "Picture mode is off. Jarvis reads the words on your screen only.",
            ScreenPicture.said(false, DesktopWrite.Outcome.Done(null)),
        )
        assertEquals("Turned off.", ScreenPicture.said(false, DesktopWrite.Outcome.Done("Turned off.")))
        assertNotNull(ScreenPicture.said(true, DesktopWrite.Outcome.Done(null)))
    }

    @Test
    fun `the words never claim it works or give a speed`() {
        val all = listOf(
            ScreenPicture.TITLE, ScreenPicture.DETAIL, ScreenPicture.SWITCH, ScreenPicture.OFF_LINE,
            ScreenPicture.WAITING_LINE, ScreenPicture.STEPS_TITLE, ScreenPicture.STEPS_NOTE,
        ).joinToString(" ").lowercase()
        assertFalse(Regex("\\bworks\\b").containsMatchIn(all.replace("what a chart", "")))
        assertFalse(Regex("\\d+ seconds").containsMatchIn(all))
        assertTrue(all.contains("slow"))
        assertTrue(all.contains("blacked out"))
        assertTrue(all.contains("never downloads the model by itself"))
    }
}
