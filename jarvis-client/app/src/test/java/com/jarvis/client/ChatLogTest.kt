package com.jarvis.client

import com.jarvis.client.net.ApiError
import com.jarvis.client.net.ChatLog
import com.jarvis.client.net.DesktopWrite
import com.jarvis.client.net.JarvisJson
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.jsonObject
import kotlinx.serialization.json.jsonPrimitive
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNotNull
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test
import java.time.LocalDate
import java.time.ZoneId

/**
 * The History screen's reading and rules - `net/ChatLog.kt`, against the
 * shapes in docs/JARVIS-API.md section 18 ("Chat history", 2026-09-24).
 */
class ChatLogTest {

    private fun obj(json: String): JsonObject = JarvisJson.parseToJsonElement(json).jsonObject

    private val listBody = """
        {"enabled": true, "recording": true, "why_not": "", "waiting": false,
         "keep_days": 0, "encrypted": true,
         "conversations": [
           {"id": "c-2", "title": "Dentist on Tuesday", "started": 1790000000,
            "updated": 1790000300, "turns": 6, "device": "phone",
            "has_voice": true, "tainted": false},
           {"id": "c-1", "title": "", "started": 1789990000,
            "updated": 1789990100, "turns": 2, "device": "desktop",
            "has_voice": false, "tainted": true},
           {"title": "no id - cannot be opened"}
         ]}
    """.trimIndent()

    @Test
    fun `the list reads the contract's fields, newest first, and drops a row with no id`() {
        val page = ChatLog.page(obj(listBody))
        assertEquals(listOf("c-2", "c-1"), page.conversations.map { it.id })
        val first = page.conversations[0]
        assertEquals("Dentist on Tuesday", first.title)
        assertEquals(1790000000L, first.started)
        assertEquals(1790000300L, first.updated)
        assertEquals(6, first.turns)
        assertEquals("phone", first.device)
        assertTrue(first.hasVoice)
        assertFalse(first.tainted)
        val second = page.conversations[1]
        assertEquals(ChatLog.UNTITLED, second.title)
        assertTrue(second.tainted)
        assertFalse(second.hasVoice)
        assertFalse("three rows is not a full page of 30", page.mayHaveOlder)
    }

    @Test
    fun `the settings half is read, and an empty why_not is no reason at all`() {
        val s = ChatLog.page(obj(listBody)).status
        assertEquals(true, s.enabled)
        assertEquals(true, s.recording)
        assertNull(s.whyNot)
        assertFalse(s.waiting)
        assertEquals(0, s.keepDays)
        assertEquals(true, s.encrypted)
    }

    @Test
    fun `a full page may have older ones, and Load older asks before the oldest shown`() {
        val rows = (1..3).joinToString(",") { """{"id":"c$it","updated":${100 - it}}""" }
        val page = ChatLog.page(obj("""{"conversations":[$rows]}"""), asked = 3)
        assertTrue(page.mayHaveOlder)
        assertEquals(97L, ChatLog.olderThan(page.conversations))
        assertEquals("/api/history?limit=30", ChatLog.listPath())
        assertEquals("/api/history?limit=30&before=97", ChatLog.listPath(97))
        assertEquals("/api/history?limit=100", ChatLog.listPath(limit = 500))
        assertNull(ChatLog.olderThan(emptyList()))
    }

    @Test
    fun `a page that repeats a row does not show it twice`() {
        val a = ChatLog.page(obj("""{"conversations":[{"id":"x","updated":5},{"id":"y","updated":4}]}""")).conversations
        val b = ChatLog.page(obj("""{"conversations":[{"id":"y","updated":4},{"id":"z","updated":3}]}""")).conversations
        assertEquals(listOf("x", "y", "z"), ChatLog.append(a, b).map { it.id })
    }

    @Test
    fun `nothing being kept is said plainly, in the PC's words`() {
        val s = ChatLog.status(
            obj("""{"enabled":true,"recording":false,"why_not":"windows credential manager could not be used","waiting":false}"""),
        )
        val line = ChatLog.stateLine(ChatLog.switchState(s, cardInQueue = false), s)
        assertTrue(line, line.startsWith("On, but nothing new is being kept right now."))
        assertTrue(line, line.contains("Windows credential manager could not be used."))
        val noReason = ChatLog.status(obj("""{"enabled":true,"recording":false}"""))
        assertTrue(ChatLog.stateLine(ChatLog.Switch.ON, noReason).endsWith("Your PC did not say why."))
    }

    @Test
    fun `one conversation reads as a transcript, with each message's source`() {
        val t = ChatLog.transcript(
            obj(
                """{"id":"c-2","title":"Dentist","tainted":true,"turns":[
                   {"role":"user","text":"an article","at":1790000000,"provenance":"shared","read_outside":false},
                   {"role":"user","text":"what is it about?","at":1790000001,"provenance":"typed","read_outside":false},
                   {"role":"assistant","text":"Teeth.","at":1790000004},
                   {"role":"user","text":"look it up","at":1790000010,"provenance":"voice","read_outside":true},
                   {"text":"no role"}
                ]}""",
            ),
        )
        assertNotNull(t)
        t!!
        assertEquals("c-2", t.id)
        assertTrue(t.tainted)
        assertEquals(listOf("user", "user", "assistant", "user"), t.turns.map { it.role })
        assertEquals(listOf("shared", "typed", null, "voice"), t.turns.map { it.provenance })
        assertEquals(listOf(false, false, false, true), t.turns.map { it.readOutside })
        assertEquals(1790000004L, t.turns[2].at)
        assertNull(ChatLog.transcript(obj("""{"turns":[]}""")))
    }

    @Test
    fun `provenance is shown quietly only when it is not typed or spoken`() {
        assertNull(ChatLog.provenanceMark("typed"))
        assertNull(ChatLog.provenanceMark("voice"))
        assertEquals("shared from another app", ChatLog.provenanceMark("shared"))
        assertEquals("pasted", ChatLog.provenanceMark("pasted"))
        assertEquals("from clipboard", ChatLog.provenanceMark("clipboard"))
        assertEquals("sent with a picture", ChatLog.provenanceMark("picture_caption"))
        assertEquals("said aloud, but not confirmed by this PC", ChatLog.provenanceMark("voice_unverified"))
    }

    @Test
    fun `a turn nobody knows the source of says so, never nothing`() {
        // Silence would read as "you typed it" (fit audit, 2026-09-24).
        assertEquals("not known where from", ChatLog.provenanceMark("unknown"))
        assertEquals("not known where from", ChatLog.provenanceMark(null))
        assertEquals("not known where from", ChatLog.provenanceMark("from_the_future"))
        assertEquals("not known where from", ChatLog.provenanceMark(""))
    }

    @Test
    fun `devices and the tainted line use the desktop's words`() {
        assertEquals("PC", ChatLog.deviceWord("desktop"))
        assertEquals("HUD", ChatLog.deviceWord("hud"))
        assertEquals("phone", ChatLog.deviceWord("phone"))
        assertEquals("unknown", ChatLog.deviceWord("toaster"))
        assertEquals("unknown", ChatLog.deviceWord(null))
        assertEquals(
            "In this conversation Jarvis read text that did not come from you - a web page, a file, " +
                "an email or another tool's output - from the marked message on.",
            ChatLog.TAINT_LINE,
        )
    }

    // ------------------------------------------------------------ switch ---

    private fun status(json: String) = ChatLog.status(obj(json))

    @Test
    fun `on is on only when the PC says so`() {
        assertEquals(ChatLog.Switch.ON, ChatLog.switchState(status("""{"enabled":true}"""), false))
        assertEquals(ChatLog.Switch.OFF, ChatLog.switchState(status("""{"enabled":false}"""), false))
        assertEquals(ChatLog.Switch.UNKNOWN, ChatLog.switchState(null, false))
        assertEquals(ChatLog.Switch.UNKNOWN, ChatLog.switchState(status("""{"enabled":"yes"}"""), false))
    }

    @Test
    fun `turning on waits for the card, from the queue or from the PC's own word`() {
        val off = status("""{"enabled":false}""")
        assertEquals(ChatLog.Switch.WAITING, ChatLog.switchState(off, cardInQueue = true))
        assertEquals(ChatLog.Switch.WAITING, ChatLog.switchState(status("""{"enabled":false,"waiting":true}"""), false))
        assertEquals(ChatLog.Switch.WAITING, ChatLog.switchState(null, cardInQueue = true))
        assertTrue(ChatLog.cardWaiting(listOf("learning_enable", "history_enable")))
        assertFalse(ChatLog.cardWaiting(listOf("learning_enable", null)))
        assertEquals(
            "Waiting for your approval to turn chat history on. Approve it on your PC or on this phone's Home screen.",
            ChatLog.stateLine(ChatLog.Switch.WAITING, off),
        )
    }

    @Test
    fun `what the switch says after a press`() {
        assertEquals(ChatLog.WAITING, ChatLog.enableSaid(true, DesktopWrite.Outcome.Waiting(null)))
        assertEquals(ChatLog.OFF_SAID, ChatLog.enableSaid(false, DesktopWrite.Outcome.Done(null)))
        assertEquals("Not changed. No.", ChatLog.enableSaid(true, DesktopWrite.Outcome.Refused("No.")))
        assertEquals("Chat history is off.", ChatLog.enableSaid(false, DesktopWrite.Outcome.Done("chat history is off")))
        // A 202 is waiting whatever its fields say - DesktopWrite's own rule.
        val r = DesktopWrite.classify(202, obj("""{"waiting":true,"enabled":false}"""))
        assertEquals(ChatLog.WAITING, ChatLog.enableSaid(true, (r as com.jarvis.client.net.ApiResult.Ok).value))
    }

    @Test
    fun `the request bodies are the contract's`() {
        assertEquals("""{"enabled":true}""", ChatLog.enabledBody(true))
        assertEquals("""{"enabled":false}""", ChatLog.enabledBody(false))
        assertEquals("""{"keep_days":90}""", ChatLog.keepDaysBody(90))
        assertNull("only 0, 30, 90 or 365", ChatLog.keepDaysBody(7))
        assertEquals("c-2\"", obj(ChatLog.deleteBody("c-2\""))["id"]!!.jsonPrimitive.content)
        assertEquals("/api/history/conversation?id=abc-DEF_1", ChatLog.conversationPath("abc-DEF_1"))
        assertEquals("/api/history/conversation?id=a%26b%3Dc", ChatLog.conversationPath("a&b=c"))
    }

    @Test
    fun `a delete is gone unless the PC says no`() {
        assertEquals(true to "Deleted from your PC.", ChatLog.deleteSaid(obj("""{"ok":true}""")))
        assertEquals(true to "Deleted.", ChatLog.deleteSaid(obj("""{"ok":true,"message":"deleted"}""")))
        assertEquals(
            false to "Not deleted. The history store is locked.",
            ChatLog.deleteSaid(obj("""{"ok":false,"error":"the history store is locked"}""")),
        )
        assertEquals(false to "Not deleted. Your PC said no, without a reason.", ChatLog.deleteSaid(obj("""{"ok":false}""")))
    }

    // --------------------------------------------------------- keep days ---

    @Test
    fun `the keep choices are the contract's four, in the owner's words`() {
        assertEquals(listOf(0, 30, 90, 365), ChatLog.KEEP_DAYS)
        assertEquals(listOf("Never", "30 days", "90 days", "1 year"), ChatLog.KEEP_DAYS.map(ChatLog::keepLabel))
    }

    @Test
    fun `a shorter limit deletes now, so it asks first - a longer one or never does not`() {
        assertTrue(ChatLog.keepNeedsConfirm(0, 30))
        assertTrue(ChatLog.keepNeedsConfirm(365, 90))
        assertTrue(ChatLog.keepNeedsConfirm(null, 365))
        assertFalse(ChatLog.keepNeedsConfirm(30, 90))
        assertFalse(ChatLog.keepNeedsConfirm(30, 0))
        assertFalse(ChatLog.keepNeedsConfirm(null, 0))
    }

    @Test
    fun `after a keep change, the PC's sentence first, else its count`() {
        assertEquals("Deleted 3 conversations.", ChatLog.keepSaid(30, obj("""{"message":"deleted 3 conversations"}""")))
        assertEquals(
            "Done. Conversations older than 30 days are deleted. 3 conversations were deleted now.",
            ChatLog.keepSaid(30, obj("""{"ok":true,"deleted":3}""")),
        )
        assertEquals(
            "Done. Conversations older than 1 year are deleted. 1 conversation was deleted now.",
            ChatLog.keepSaid(365, obj("""{"deleted":1}""")),
        )
        assertEquals("Done. Conversations are kept until you delete them.", ChatLog.keepSaid(0, null))
    }

    // ------------------------------------------------------------- rows ---

    @Test
    fun `when a conversation was, in plain words`() {
        val zone = ZoneId.of("UTC")
        val today = LocalDate.of(2026, 9, 24)
        val noon = today.atStartOfDay(zone).plusHours(12).toEpochSecond()
        assertEquals("Today 12:00", ChatLog.whenLine(noon, zone, today))
        assertEquals("Yesterday 12:00", ChatLog.whenLine(noon - 86_400, zone, today))
        assertEquals("12 Sep 12:00", ChatLog.whenLine(noon - 12 * 86_400, zone, today))
        assertEquals("3 Jan 2025", ChatLog.whenLine(LocalDate.of(2025, 1, 3).atStartOfDay(zone).toEpochSecond(), zone, today))
        assertEquals("When unknown", ChatLog.whenLine(null, zone, today))
        val row = ChatLog.page(obj(listBody)).conversations[1]
        assertEquals("PC", ChatLog.deviceWord(row.device))
        assertTrue(ChatLog.rowLine(row, zone, today).endsWith("PC · 2 messages"))
    }

    @Test
    fun `a missing conversation and a missing feature are said in words`() {
        assertNotNull(ChatLog.failure(ApiError.NotFound))
        assertNotNull(ChatLog.failure(ApiError.NotAvailable))
        assertNull(ChatLog.failure(ApiError.BadToken))
    }

    @Test
    fun `the wording is the contract's`() {
        assertEquals("Keep chat history on this PC", ChatLog.SWITCH)
        assertEquals(
            "Your chats, including what you say to Jarvis by voice, are kept on this PC, encrypted. " +
                "Nothing is sent anywhere.",
            ChatLog.UNDER,
        )
        assertEquals(
            "Chat history is off. Nothing new is kept. What is already kept stays until you delete it.",
            ChatLog.OFF_SAID,
        )
        assertEquals("Delete conversations older than", ChatLog.KEEP_TITLE)
    }
}
