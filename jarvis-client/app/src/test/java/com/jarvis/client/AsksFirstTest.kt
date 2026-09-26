package com.jarvis.client

import com.jarvis.client.net.ApiError
import com.jarvis.client.net.AsksFirst
import com.jarvis.client.net.JarvisJson
import com.jarvis.client.net.PendingItem
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.buildJsonObject
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
 * Mind's "What asks first" (the owner's decisions of 2026-09-26), read from
 * what the PC REALLY answers.
 *
 * `contract/asks-first-cases.json` is the real `GET /api/asks_first` answer
 * (jarvis_asks_first.view()), written by tools/gen_asks_first_cases.py -
 * byte for byte the file the desktop builds against.
 */
class AsksFirstTest {

    private val doc: JsonObject = run {
        val text = requireNotNull(javaClass.classLoader?.getResource("contract/asks-first-cases.json")) {
            "contract/asks-first-cases.json is missing - run tools/gen_asks_first_cases.py"
        }.readText()
        JarvisJson.parseToJsonElement(text) as JsonObject
    }
    private val cases = doc["cases"]!!.jsonObject
    private val words = doc["words"]!!.jsonObject

    private fun view(case: String): AsksFirst.View =
        requireNotNull(AsksFirst.parse(cases[case]!!.jsonObject)) { "$case did not parse" }

    private fun word(key: String) = words[key]!!.jsonPrimitive.content

    private fun row(v: AsksFirst.View, id: String) = v.groups.flatMap { it.rows }.first { it.id == id }

    @Test
    fun `the words are the PC's own`() {
        assertEquals(word("title"), AsksFirst.TITLE)
        assertEquals(word("detail"), AsksFirst.DETAIL)
        assertEquals(word("missing"), AsksFirst.MISSING)
        assertEquals(word("switch_label"), AsksFirst.SWITCH_LABEL)
        assertEquals(word("waiting"), AsksFirst.WAITING)
        assertEquals(word("phone_loosen"), AsksFirst.PHONE_LOOSEN)
        assertEquals(word("lights_label"), AsksFirst.LIGHTS_LABEL)
        assertEquals(word("lights_detail"), AsksFirst.LIGHTS_DETAIL)
        assertEquals(word("lights_waiting"), AsksFirst.LIGHTS_WAITING)
        assertEquals(doc["switchable"]!!.jsonArray.map { it.jsonPrimitive.content }, AsksFirst.SWITCHABLE)
    }

    @Test
    fun `every real view is read, every group and row in the PC's order`() {
        for (name in cases.keys) {
            val v = view(name)
            val raw = cases[name]!!.jsonObject["groups"]!!.jsonArray
            assertEquals(name, raw.map { it.jsonObject["title"]!!.jsonPrimitive.content }, v.groups.map { it.title })
            assertEquals(
                name,
                raw.flatMap { g -> g.jsonObject["rows"]!!.jsonArray.map { it.jsonObject["id"]!!.jsonPrimitive.content } },
                v.groups.flatMap { g -> g.rows.map { it.id } },
            )
            assertTrue(name, v.groups.flatMap { it.rows }.filter { it.switch != null }.all { it.action in AsksFirst.SWITCHABLE })
        }
    }

    @Test
    fun `the phone makes things stricter and never looser`() {
        val phone = view("phone_shipped")
        assertFalse(phone.canLoosen)
        val cal = row(phone, "calendar_read")
        val sw = requireNotNull(AsksFirst.switchView(cal, phone))
        assertFalse("shipped: it goes ahead without asking", sw.checked)
        assertTrue("turning it ON (stricter) is offered", sw.enabled)
        val strict = view("pc_stricter_lights_on")
        val cal2 = requireNotNull(AsksFirst.switchView(row(strict, "calendar_read"), strict))
        assertTrue(cal2.checked)
        assertFalse("once it asks, the phone cannot turn it off", cal2.enabled)
        assertTrue(AsksFirst.stricterBody("calendar_read")!!.contains("\"ask\":true"))
        assertNull("nothing off the list is ever sent", AsksFirst.stricterBody("send_email"))
        assertNull("sending email has no switch", AsksFirst.switchView(row(phone, "send_email"), phone))
        val note = row(view("phone_cards_waiting"), "calendar_read").note
        assertTrue("the row says where to loosen it", note.contains(AsksFirst.PHONE_LOOSEN))
    }

    @Test
    fun `a waiting card and the lights setting`() {
        val v = view("phone_cards_waiting")
        val sw = requireNotNull(AsksFirst.switchView(row(v, "calendar_read"), v))
        assertTrue(sw.checked)
        assertEquals(listOf(AsksFirst.WAITING), sw.lines)
        val lights = AsksFirst.lightsView(v.lights, live = true)
        assertTrue(lights.checked)
        assertEquals(listOf(AsksFirst.LIGHTS_WAITING), lights.lines)
        val off = AsksFirst.lightsView(view("pc_shipped").lights, live = false)
        assertFalse("ON is held on a stale link", off.canChange)
        val on = AsksFirst.lightsView(view("pc_stricter_lights_on").lights, live = false)
        assertTrue("OFF is never held", on.canChange)
        assertEquals("{\"enabled\":false}", AsksFirst.lightsBody(false))
    }

    @Test
    fun `a loosening card cannot be approved on the phone`() {
        val card = PendingItem(id = "r1", action = AsksFirst.LOOSEN_ACTION)
        assertTrue(card.pcOnly)
        assertFalse(PendingItem(id = "r2", action = "send_email").pcOnly)
        assertTrue(AsksFirst.APPROVE_ON_PC.contains("Deny still works"))
    }

    @Test
    fun `an older PC says so`() {
        assertNull(AsksFirst.parse(buildJsonObject { put("available", false) }))
        assertTrue(AsksFirst.missing(ApiError.NotFound))
        assertTrue(AsksFirst.missing(ApiError.NotAvailable))
    }
}
