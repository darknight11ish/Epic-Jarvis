package com.jarvis.client

import com.jarvis.client.net.ForgetRange
import kotlinx.serialization.json.Json
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.jsonArray
import kotlinx.serialization.json.jsonObject
import kotlinx.serialization.json.jsonPrimitive
import kotlinx.serialization.json.int
import kotlinx.serialization.json.long
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNotNull
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test

/**
 * "Forget a time frame" on the phone (the owner's decision of 2026-09-28),
 * read from what the PC REALLY answers.
 *
 * `contract/forget-range-cases.json` is written by
 * tools/gen_forget_range_cases.py from the real backend
 * (jarvis_forget_range.py) - byte for byte the file the desktop's
 * forget-range.mjs and brain/forget_range.rs build against. Its `words` are
 * the screens' sentences in both apps.
 */
class ForgetRangeTest {

    private val json = Json { ignoreUnknownKeys = true }

    private val doc: JsonObject = run {
        val text = requireNotNull(javaClass.classLoader?.getResource("contract/forget-range-cases.json")) {
            "contract/forget-range-cases.json is missing - run tools/gen_forget_range_cases.py"
        }.readText()
        json.parseToJsonElement(text) as JsonObject
    }
    private val cases = doc["cases"]!!.jsonObject

    private fun body(name: String): JsonObject = cases[name]!!.jsonObject["body"]!!.jsonObject
    private fun status(name: String): Int = cases[name]!!.jsonObject["status"]!!.jsonPrimitive.int

    @Test
    fun `the words are the desktop's, word for word`() {
        val words = doc["words"]!!.jsonObject
        assertEquals(words.keys, ForgetRange.WORDS.keys)
        for ((k, v) in words) assertEquals(k, v.jsonPrimitive.content, ForgetRange.WORDS[k])
        assertEquals(words["missing"]!!.jsonPrimitive.content, ForgetRange.MISSING)
        val presets = doc["presets"]!!.jsonArray.map {
            it.jsonObject["id"]!!.jsonPrimitive.content to it.jsonObject["label"]!!.jsonPrimitive.content
        }
        assertEquals(presets, ForgetRange.PRESETS.map { it.id to it.label })
        val routes = doc["routes"]!!.jsonObject
        assertEquals(routes["status"]!!.jsonPrimitive.content, ForgetRange.PATH)
        assertEquals(routes["preview"]!!.jsonPrimitive.content, ForgetRange.PREVIEW_PATH)
        assertEquals(routes["undo"]!!.jsonPrimitive.content, ForgetRange.UNDO_PATH)
    }

    @Test
    fun `every status reads`() {
        val fresh = ForgetRange.parseStatus(body("status_fresh"))
        assertTrue(fresh.available)
        assertFalse(fresh.waiting)
        assertNull(fresh.undo)
        assertEquals(200, fresh.maxItems)
        assertEquals(ForgetRange.PRESETS, fresh.presets)
        assertTrue(ForgetRange.parseStatus(body("status_waiting")).waiting)
        val undo = requireNotNull(ForgetRange.parseStatus(body("status_undo")).undo)
        assertEquals(2, undo.facts)
        assertEquals(2, undo.chats)
        assertEquals(10, undo.minutesLeft)
        assertEquals(
            "Forgot 2 facts and deleted 2 chats from 1 to 15 September 2026. 10 min left to undo.",
            ForgetRange.undoLine(undo),
        )
        val asked = requireNotNull(ForgetRange.parseStatus(body("status_asked")).asked)
        assertEquals(listOf("2026-09-01", "2026-09-15", "1 to 15 September 2026"),
            listOf(asked.from, asked.to, asked.said))
        assertEquals(listOf("facts"), asked.kinds)
        assertEquals("Nothing was forgotten - you said no.",
            ForgetRange.parseStatus(body("status_denied")).last?.message)
        assertFalse(ForgetRange.parseStatus(null).available)
        assertEquals(ForgetRange.MISSING, ForgetRange.parseStatus(null).why)
    }

    @Test
    fun `the list reads, starts all ticked, and only the ticked ids are sent`() {
        val p = ForgetRange.parsePreview(body("preview"))
        assertEquals("1 to 15 September 2026", p.frameSaid)
        assertEquals(listOf("The owner moved to Leeds in 2019", "The owner's sister likes jazz"), p.facts.map { it.text })
        assertTrue(p.facts[1].pinned && p.facts[1].betweenUs)
        assertEquals(listOf("Help me write a poem" to true, "Plan the trip to Rome" to false),
            p.chats.map { it.title to it.spills })
        assertEquals("2 facts and 2 chats from 1 to 15 September 2026.", p.said)
        val all = ForgetRange.allTicked(p)
        assertEquals(4, ForgetRange.tickedCount(p, all))
        val some = all - "fact:${p.facts[0].id}" - "chat:conv-poem-00002"
        val sent = json.parseToJsonElement(ForgetRange.forgetBody(p, some)).jsonObject
        assertEquals("2026-09-01", sent["from"]!!.jsonPrimitive.content)
        assertEquals("2026-09-15", sent["to"]!!.jsonPrimitive.content)
        assertEquals(listOf(p.facts[1].id), sent["facts"]!!.jsonArray.map { it.jsonPrimitive.long })
        assertEquals(listOf("conv-trip-00001"), sent["chats"]!!.jsonArray.map { it.jsonPrimitive.content })
        assertEquals("Forget these (2)", ForgetRange.forgetLabel(2))

        val many = ForgetRange.parsePreview(body("preview_too_many"))
        assertTrue(many.tooMany)
        assertTrue(many.facts.isEmpty())
        assertEquals(201, many.factsCount)
        assertTrue(ForgetRange.parsePreview(body("preview_empty")).empty)
        assertFalse(ForgetRange.parsePreview(null).available)
    }

    @Test
    fun `only a choice or two real dates reach the query`() {
        val both = setOf("facts", "chats")
        assertEquals("/api/memory/forget_range/preview?preset=last_week&kinds=facts,chats",
            ForgetRange.previewPath("last_week", null, null, both))
        assertEquals("/api/memory/forget_range/preview?from=2026-09-01&to=2026-09-28T11:59&kinds=chats",
            ForgetRange.previewPath(null, "2026-09-01", "2026-09-28T11:59", setOf("chats")))
        for (bad in listOf("2026-9-1", "2026-09-01&x=1", "1 Sept", "")) {
            assertNull(bad, ForgetRange.previewPath(null, bad, "2026-09-02", both))
        }
        assertNull(ForgetRange.previewPath("forever", null, null, both))
        assertNull(ForgetRange.previewPath("today", null, null, emptySet()))
    }

    @Test
    fun `answers read the way the screen expects`() {
        val waiting = ForgetRange.said(ForgetRange.Reply(status("forget_waiting"), body("forget_waiting")), "")
        assertTrue(waiting.waiting)
        assertTrue(waiting.said.startsWith("Waiting for your approval"))
        val changed = ForgetRange.said(ForgetRange.Reply(status("forget_list_changed"), body("forget_list_changed")), "")
        assertFalse(changed.done)
        assertTrue(changed.listChanged)
        assertTrue(changed.said.startsWith("The list changed"))
        val undo = ForgetRange.said(ForgetRange.Reply(status("undo"), body("undo")), "")
        assertTrue(undo.done)
        assertEquals("Put back: 2 facts and 2 chats.", undo.said)
        val none = ForgetRange.said(ForgetRange.Reply(status("undo_nothing"), body("undo_nothing")), "")
        assertFalse(none.done)
        assertTrue(none.said.startsWith("There is nothing to undo"))
        val missing = doc["missing"]!!.jsonObject
        val m = ForgetRange.Reply(missing["status"]!!.jsonPrimitive.int, missing["body"]!!.jsonObject)
        assertTrue(ForgetRange.isMissing(m))
        assertEquals(ForgetRange.MISSING, ForgetRange.said(m, "").said)
        assertFalse("its own 404 is not 'missing'",
            ForgetRange.isMissing(ForgetRange.Reply(404, json.parseToJsonElement("""{"ok": false}""").jsonObject)))
    }

    @Test
    fun `forget waits for a live link, Undo never`() {
        assertTrue(ForgetRange.heldOnStale("forget"))
        assertFalse(ForgetRange.heldOnStale("undo"))
    }

    @Test
    fun `the Jarvis bar's answer opens this one place only`() {
        assertEquals(ForgetRange.PLACE,
            ForgetRange.openFromRoute("""{"quick": "forget_range", "open_brain": "forget-range"}"""))
        assertNull(ForgetRange.openFromRoute("""{"open_brain": "somewhere-else"}"""))
        assertNull(ForgetRange.openFromRoute("""{"open_brain": 3}"""))
        assertNull(ForgetRange.openFromRoute("not json"))
        assertNull(ForgetRange.openFromRoute(null))
        val said = cases["asked_said"]!!.jsonObject
        assertTrue(said["said"]!!.jsonPrimitive.content.contains("in Brain, under Forget a time frame"))
        assertNotNull(said["opens"])
    }
}
