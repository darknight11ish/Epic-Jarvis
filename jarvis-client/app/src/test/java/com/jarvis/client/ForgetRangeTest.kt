package com.jarvis.client

import com.jarvis.client.net.ForgetRange
import kotlinx.serialization.json.Json
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.boolean
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
        assertEquals(routes["confirm"]!!.jsonPrimitive.content, ForgetRange.CONFIRM_PATH)
        assertEquals(120, doc["limits"]!!.jsonObject["confirm_seconds"]!!.jsonPrimitive.int)
    }

    /**
     * The words the contract's `words` map does not carry (the apps lane's
     * half of the 2026-11-04 feature). Five are the PC's own constants and the
     * sixth is this screen's one line about the time left; the desktop says
     * all six word for word (src/forget-range.js EXTRA), and its tests pin
     * them to `backend/jarvis_forget_range.py`.
     */
    @Test
    fun `the extra words are the desktop's, word for word`() {
        assertEquals(
            setOf("confirm_text", "confirm_yes", "hold_left", "pinned_many", "pinned_one", "pinned_why"),
            ForgetRange.EXTRA.keys,
        )
        val confirmWords = doc["confirm_words"]!!.jsonObject
        assertEquals(confirmWords["yes"]!!.jsonPrimitive.content, ForgetRange.x("confirm_yes"))
        assertEquals(confirmWords["text"]!!.jsonPrimitive.content, ForgetRange.x("confirm_text"))
        assertEquals("1 pinned chat is kept", ForgetRange.pinnedKeptLine(1))
        assertEquals("3 pinned chats are kept", ForgetRange.pinnedKeptLine(3))
        assertEquals("2 min left to say yes",
            ForgetRange.holdLeftLine(ForgetRange.Confirm("hold-id", 120, ForgetRange.x("confirm_text"))))
        assertEquals("1 min left to say yes",
            ForgetRange.holdLeftLine(ForgetRange.Confirm("hold-id", 5, "")))
        assertEquals("1 message", ForgetRange.messagesLine(1))
        assertEquals("12 messages", ForgetRange.messagesLine(12))
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
        // A chat that spills outside the days starts UNticked (the second chat audit).
        assertEquals(3, ForgetRange.tickedCount(p, all))
        assertFalse("chat:conv-poem-00002" in all)
        val some = all - "fact:${p.facts[0].id}"
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
        // The second yes deletes, so it waits for a live link too.
        assertTrue(ForgetRange.heldOnStale("confirm"))
    }

    /**
     * The extended feature's answers (owner, 2026-11-04): the pinned chats
     * kept, the measured estimate, and the held second yes. Every body here is
     * the real backend's (`contract/forget-range-cases.json`).
     */
    @Test
    fun `the pinned chats are kept, never ticked, never sent - and the estimate is read`() {
        val p = ForgetRange.parsePreview(body("preview_pinned"))
        assertEquals(1, p.pinnedKeptCount)
        assertEquals(listOf(ForgetRange.PinnedChat("conv-pinned-01", "Pinned planning", 1)), p.pinnedKept)
        // Never on the tickable list, so never ticked, counted or sent.
        assertEquals(listOf("conv-poem-00002", "conv-trip-00001"), p.chats.map { it.id })
        val all = ForgetRange.allTicked(p)
        assertFalse("chat:conv-pinned-01" in all)
        assertEquals(3, ForgetRange.tickedCount(p, all))
        val sent = json.parseToJsonElement(ForgetRange.forgetBody(p, all + "chat:conv-pinned-01")).jsonObject
        assertEquals(listOf("conv-trip-00001"), sent["chats"]!!.jsonArray.map { it.jsonPrimitive.content })
        assertEquals("1 pinned chat is kept", ForgetRange.pinnedKeptLine(p.pinnedKeptCount))
        // The measured estimate, said before the owner is asked.
        assertEquals(
            ForgetRange.Estimate(2, 2, 3, 1, "About 1 second to forget 2 facts and delete 2 chats (3 messages)."),
            p.estimate,
        )
        assertEquals(p.estimate, ForgetRange.parsePreview(body("preview")).estimate)
        // A list with no pinned chats carries none of them, and an empty
        // count falls back to what the list actually holds.
        assertTrue(ForgetRange.parsePreview(body("preview")).pinnedKept.isEmpty())
        assertEquals(0, ForgetRange.parsePreview(body("preview")).pinnedKeptCount)
    }

    @Test
    fun `the second yes is the held id and a literal true`() {
        val held = ForgetRange.parseStatus(body("status_confirm"))
        val c = requireNotNull(held.confirm)
        assertEquals("hold-id", c.id)
        assertEquals(120, c.expiresIn)
        assertEquals(ForgetRange.x("confirm_text"), c.text)
        assertFalse(held.waiting)
        val sent = ForgetRange.confirmBody(c.id)
        assertEquals("""{"id":"hold-id","yes":true}""", sent)
        val obj = json.parseToJsonElement(sent).jsonObject
        assertEquals("hold-id", obj["id"]!!.jsonPrimitive.content)
        assertTrue("the yes is not the literal boolean true", obj["yes"]!!.jsonPrimitive.boolean)
        assertTrue(ForgetRange.isHoldId("0123456789abcdef0123456789abcdef"))
        assertTrue(ForgetRange.isHoldId("hold-id"))
        for (bad in listOf("", "hold id", "a".repeat(129))) {
            assertFalse(bad, ForgetRange.isHoldId(bad))
        }
        assertFalse(ForgetRange.isHoldId(null))
        // Nothing is held unless the PC says so: no block, a block with no id
        // this screen could hand back, or an ended hold are all "no second yes".
        assertNull(ForgetRange.parseStatus(body("status_confirm_expired")).confirm)
        assertNull(ForgetRange.parseStatus(body("status_fresh")).confirm)
        assertNull(ForgetRange.parseStatus(body("status_waiting")).confirm)
        assertEquals("The second yes timed out. Nothing was forgotten or deleted.",
            ForgetRange.parseStatus(body("status_confirm_expired")).last?.message)
        assertEquals(0, ForgetRange.parseStatus(body("status_confirm")).pinnedKeptCount)
    }

    @Test
    fun `every refusal of the second yes is read in the PC's own words`() {
        for (name in listOf(
            "confirm_not_literal", "confirm_wrong_id", "confirm_twice", "confirm_while_card",
            "confirm_before_card", "confirm_no_hold", "confirm_expired",
        )) {
            val out = ForgetRange.said(ForgetRange.Reply(status(name), body(name)), ForgetRange.w("waiting"))
            assertFalse(name, out.done)
            assertFalse(name, out.waiting)
            assertEquals(name, body(name)["error"]!!.jsonPrimitive.content, out.said)
        }
    }

    @Test
    fun `hidden lists lose the pinned chats' titles too`() {
        val p = ForgetRange.parsePreview(body("preview_pinned"))
        assertTrue(p.facts[0].text.isNotEmpty())
        val hidden = ForgetRange.redact(p)
        assertTrue(hidden.hidden)
        assertEquals("", hidden.pinnedKept.single().title)
        assertEquals("conv-pinned-01", hidden.pinnedKept.single().id)
        assertEquals("a count is not a word", 1, hidden.pinnedKeptCount)
        assertEquals(1, hidden.pinnedKept.single().messages)
        assertTrue(hidden.facts.all { it.text.isEmpty() })
        assertTrue(hidden.chats.all { it.title.isEmpty() })
        // Every word this list carried is gone. The IDs stay (they are the
        // opaque keys a tick and a send use, and "conv-poem-00002" is one of
        // them, which is why this looks at the words and not at the whole
        // object).
        val words = (hidden.facts.map { it.text } + hidden.chats.map { it.title } +
            hidden.pinnedKept.map { it.title }).joinToString("|")
        for (never in listOf("Pinned planning", "Leeds", "jazz", "poem", "Rome")) {
            assertFalse(never, words.contains(never))
        }
        // The estimate is numbers and dates only, so it stays.
        assertEquals(p.estimate, hidden.estimate)
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
