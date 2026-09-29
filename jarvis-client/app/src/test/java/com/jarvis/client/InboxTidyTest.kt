package com.jarvis.client

import com.jarvis.client.net.InboxTidy
import kotlinx.serialization.json.Json
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.buildJsonObject
import kotlinx.serialization.json.int
import kotlinx.serialization.json.jsonArray
import kotlinx.serialization.json.jsonObject
import kotlinx.serialization.json.jsonPrimitive
import kotlinx.serialization.json.put
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNotNull
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test

/**
 * "Inbox tidy by voice" on the phone (the owner's decision of 2026-09-28),
 * read from what the PC REALLY answers.
 *
 * `contract/inbox-tidy-cases.json` is written by tools/gen_inbox_tidy_cases.py
 * from the real backend (jarvis_inbox_tidy.py) against a stand-in mail server -
 * byte for byte the file the desktop's inbox-tidy.mjs and brain/inbox_tidy.rs
 * build against. Its `words` are the strip's sentences in both apps, and its
 * `strip` rows are what the strip says in each situation.
 */
class InboxTidyTest {

    private val json = Json { ignoreUnknownKeys = true }

    private val doc: JsonObject = run {
        val text = requireNotNull(javaClass.classLoader?.getResource("contract/inbox-tidy-cases.json")) {
            "contract/inbox-tidy-cases.json is missing - run tools/gen_inbox_tidy_cases.py"
        }.readText()
        json.parseToJsonElement(text) as JsonObject
    }
    private val cases = doc["cases"]!!.jsonObject

    private fun body(name: String): JsonObject = cases[name]!!.jsonObject["body"]!!.jsonObject
    private fun code(name: String): Int = cases[name]!!.jsonObject["status"]!!.jsonPrimitive.int
    private fun reply(name: String) = InboxTidy.Reply(code(name), body(name))

    @Test
    fun `the words are the desktop's, word for word`() {
        val words = doc["words"]!!.jsonObject
        assertEquals(words.keys, InboxTidy.WORDS.keys)
        for ((k, v) in words) assertEquals(k, v.jsonPrimitive.content, InboxTidy.WORDS[k])
        assertEquals(words["missing"]!!.jsonPrimitive.content, InboxTidy.MISSING)
        val routes = doc["routes"]!!.jsonObject
        assertEquals(routes["status"]!!.jsonPrimitive.content, InboxTidy.PATH)
        assertEquals(routes["undo"]!!.jsonPrimitive.content, InboxTidy.UNDO_PATH)
        assertEquals(10, doc["undo_minutes"]!!.jsonPrimitive.int)
    }

    @Test
    fun `every real status reads`() {
        val idle = InboxTidy.parseStatus(body("status_idle"))
        assertTrue(idle.available)
        assertNull(idle.undo)
        val open = requireNotNull(InboxTidy.parseStatus(body("status_undo")).undo)
        assertEquals(3, open.count)
        assertEquals("archive", open.action)
        assertEquals("Archived 3 emails.", open.said)
        assertEquals(10, open.minutesLeft)
        assertEquals(0, open.more)
        val two = requireNotNull(InboxTidy.parseStatus(body("status_undo_two")).undo)
        assertEquals("mark_read", two.action)
        assertEquals(1, two.more)
        assertEquals(1, InboxTidy.parseStatus(body("status_undo_last_minute")).undo!!.minutesLeft)
        assertNull(InboxTidy.parseStatus(null).undo)
        assertFalse(InboxTidy.parseStatus(null).available)
        // Not an Undo: no words, or no minutes.
        assertNull(InboxTidy.parseStatus(buildJsonObject { put("undo", buildJsonObject { put("said", "x") }) }).undo)
        assertNull(
            InboxTidy.parseStatus(
                buildJsonObject { put("undo", buildJsonObject { put("minutes_left", 3) }) },
            ).undo,
        )
    }

    @Test
    fun `the strip says what the contract's rows say, in every situation`() {
        val rows = doc["strip"]!!.jsonArray
        assertTrue(rows.size >= 20)
        for (r in rows) {
            val row = r.jsonObject
            val name = row["case"]!!.jsonPrimitive.content
            val locked = row["locked"]!!.jsonPrimitive.content.toBoolean()
            val stale = row["stale"]!!.jsonPrimitive.content.toBoolean()
            val got = InboxTidy.strip(InboxTidy.parseStatus(body(name)), locked, stale)
            val expect = row["expect"]
            val label = "$name locked=$locked stale=$stale"
            if (expect == null || expect.toString() == "null") {
                assertNull(label, got)
            } else {
                val e = expect.jsonObject
                assertNotNull(label, got)
                assertEquals(label, e["text"]!!.jsonPrimitive.content, got!!.text)
                assertEquals(label, e["left"]!!.jsonPrimitive.content, got.left)
                assertEquals(label, e["can_undo"]!!.jsonPrimitive.content.toBoolean(), got.canUndo)
                assertEquals(label, e["note"]!!.jsonPrimitive.content, got.note)
            }
        }
    }

    @Test
    fun `locked shows no count and no action, and Undo waits`() {
        val s = requireNotNull(InboxTidy.strip(InboxTidy.parseStatus(body("status_undo_two")), locked = true, stale = false))
        assertEquals(InboxTidy.w("hidden"), s.text)
        assertFalse(s.canUndo)
        assertEquals(InboxTidy.w("locked"), s.note)
        assertFalse(s.text.contains("Archived"))
        assertFalse(s.text.contains("earlier"))
    }

    @Test
    fun `a stale link holds Undo and says why`() {
        val s = requireNotNull(InboxTidy.strip(InboxTidy.parseStatus(body("status_undo")), locked = false, stale = true))
        assertFalse(s.canUndo)
        assertEquals(InboxTidy.w("stale"), s.note)
        assertEquals("Archived 3 emails.", s.text)
    }

    @Test
    fun `the minutes run down and an Undo out of time is gone`() {
        val st = InboxTidy.parseStatus(body("status_undo"))          // 570 seconds left when read
        assertEquals(10, InboxTidy.aged(st, 0).undo!!.minutesLeft)
        assertEquals(9, InboxTidy.aged(st, 30_000).undo!!.minutesLeft)
        assertEquals(540, InboxTidy.aged(st, 30_000).undo!!.secondsLeft)
        assertEquals(1, InboxTidy.aged(st, 569_000).undo!!.minutesLeft)
        assertNull(InboxTidy.aged(st, 570_000).undo)
        assertNull(InboxTidy.aged(st, 99_999_999).undo)
        assertNull(InboxTidy.aged(InboxTidy.parseStatus(body("status_idle")), 5_000).undo)
        assertEquals("3 min left to undo", InboxTidy.leftWords(3))
    }

    @Test
    fun `every real Undo answer reads`() {
        val done = InboxTidy.undoOutcome(reply("undo_done"))
        assertTrue(done.done)
        assertEquals(body("undo_done")["message"]!!.jsonPrimitive.content, done.message)
        val some = InboxTidy.undoOutcome(reply("undo_some_lost"))
        assertTrue(some.done)
        assertTrue(some.message.contains("could not be put back"))
        for (name in listOf("undo_nothing", "undo_unreachable")) {
            val out = InboxTidy.undoOutcome(reply(name))
            assertFalse(name, out.done)
            assertEquals(name, body(name)["error"]!!.jsonPrimitive.content, out.message)
        }
        assertTrue(InboxTidy.undoOutcome(reply("undo_unreachable")).message.contains("can still be undone"))
    }

    @Test
    fun `a PC without the routes says so`() {
        val m = doc["missing"]!!.jsonObject
        val r = InboxTidy.Reply(m["status"]!!.jsonPrimitive.int, m["body"]!!.jsonObject)
        assertTrue(InboxTidy.missing(r))
        assertEquals(InboxTidy.MISSING, InboxTidy.undoOutcome(r).message)
        assertFalse(InboxTidy.undoOutcome(r).done)
        assertEquals(InboxTidy.MISSING, InboxTidy.undoOutcome(InboxTidy.Reply(501, null)).message)
        // The PC's own "no such route" is a sentence, not "missing".
        val own = buildJsonObject {
            put("ok", false)
            put("error", "No such route")
        }
        assertEquals("No such route", InboxTidy.undoOutcome(InboxTidy.Reply(404, own)).message)
        assertFalse(InboxTidy.undoOutcome(InboxTidy.Reply(200, null)).done)
    }

    @Test
    fun `the strip holds no sender and no subject, and the file holds none either`() {
        val blob = doc.toString()
        for (word in listOf("Shop Weekly", "weekly digest", "news@shop", "Sam Smith", "Lunch on Friday")) {
            assertFalse(word, blob.contains(word))
        }
        assertTrue(
            "the phone asks the PC only for the status and Undo",
            InboxTidy.PATH == "/api/email/tidy" && InboxTidy.UNDO_PATH == "/api/email/tidy/undo",
        )
    }
}
