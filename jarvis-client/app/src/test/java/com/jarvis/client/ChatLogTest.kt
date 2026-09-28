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
    fun `the search box narrows the loaded list by title, case-insensitively, and asks nothing`() {
        // Ease-of-use audit row 20; the owner's answer of 2026-09-27: "shown
        // on screen only; nothing saved, nothing handed to the AI" - pure
        // client-side filtering, the same shape as the desktop's.
        val rows = ChatLog.page(obj(listBody)).conversations
        assertEquals(2, rows.size)
        assertEquals(listOf("Dentist on Tuesday"), ChatLog.filtered(rows, "dentist").map { it.title })
        assertEquals(listOf("Dentist on Tuesday"), ChatLog.filtered(rows, "DENTIST").map { it.title })
        assertEquals(rows, ChatLog.filtered(rows, ""))
        assertEquals(rows, ChatLog.filtered(rows, "   "))
        assertTrue(ChatLog.filtered(rows, "zzz-nothing").isEmpty())
    }

    // ---- "Search what was said" and "Find in this chat" (section 71) ----

    @Test
    fun `a word search is sent only with two letters or more, encoded so nothing can add a parameter`() {
        assertEquals("/api/history/search?q=dentist&limit=20", ChatLog.searchPath("dentist"))
        assertEquals("/api/history/search?q=mill+road&limit=20", ChatLog.searchPath("  mill   road "))
        assertEquals(
            "/api/history/search?q=a%26limit%3D999%23x&limit=5",
            ChatLog.searchPath("a&limit=999#x", limit = 5),
        )
        assertNull(ChatLog.searchPath("a"))
        assertNull(ChatLog.searchPath("   "))
        assertNull(ChatLog.searchPath("x".repeat(101)))
        assertEquals("/api/history/search?q=bread&limit=50", ChatLog.searchPath("bread", limit = 500))
    }

    @Test
    fun `the PC's search answer is read as it is sent, snippet parts and all`() {
        val body = obj(
            """
            {"enabled": true, "query_ok": true, "why": "", "more": true, "partial": false, "searched": 40,
             "conversations": [
               {"id": "c-1", "title": "Dentist on Tuesday", "updated": 1790000300, "turns": 4,
                "device": "phone", "has_voice": false, "tainted": true, "hits": 2,
                "snippet": {"role": "assistant", "at": 1790000200, "before": true, "after": false,
                            "parts": [{"text": "at 3, on ", "hit": false}, {"text": "Mill", "hit": true},
                                      {"text": 5, "hit": true}]}},
               {"title": "no id"}
             ]}
            """.trimIndent(),
        )
        val s = ChatLog.search(body)
        assertTrue(s.queryOk)
        assertTrue(s.more)
        assertEquals(1, s.found.size)
        val f = s.found[0]
        assertEquals("c-1", f.row.id)
        assertTrue(f.row.tainted)
        assertEquals(2, f.hits)
        assertEquals("assistant", f.snippet.role)
        assertTrue(f.snippet.cutBefore)
        assertEquals(listOf(ChatLog.Part("at 3, on ", false), ChatLog.Part("Mill", true)), f.snippet.parts)
        assertEquals("Jarvis: ", ChatLog.snippetWho(f.snippet))
        assertEquals("found in 2 messages", ChatLog.hitsLine(2))
        assertNull(ChatLog.hitsLine(0))
        assertTrue(ChatLog.searchMoreLine(s)!!.contains("newest matches only"))
        val refused = ChatLog.search(obj("""{"query_ok": false, "why": "Type at least two letters.", "conversations": []}"""))
        assertFalse(refused.queryOk)
        assertEquals("Type at least two letters.", refused.why)
    }

    @Test
    fun `a PC without the search is told apart from a failure`() {
        assertTrue(ChatLog.searchMissing(ApiError.NotFound))
        assertTrue(ChatLog.searchMissing(ApiError.Server(501, "")))
        assertFalse(ChatLog.searchMissing(ApiError.Server(500, "")))
        assertFalse(ChatLog.searchMissing(ApiError.NotAvailable))
    }

    @Test
    fun `find in this chat counts every place, in reading order, and the words are words`() {
        val turns = listOf(
            ChatLog.Turn("user", "Mill Road, then mill road again", null, null, false),
            ChatLog.Turn("assistant", "no", null, null, false),
            ChatLog.Turn("assistant", "Road!", null, null, false),
        )
        val m = ChatLog.findMatches(turns, "mill road")
        assertEquals(
            listOf(0 to "Mill", 0 to "Road", 0 to "mill", 0 to "road", 2 to "Road"),
            m.map { it.turn to turns[it.turn].text.substring(it.start, it.end) },
        )
        assertTrue(ChatLog.findMatches(turns, "(.*)").isEmpty())
        assertTrue(ChatLog.findMatches(turns, "  ").isEmpty())
        assertEquals(ChatLog.FIND_NONE, ChatLog.findCount(0, 0))
        assertEquals("1 match", ChatLog.findCount(0, 1))
        assertEquals("3 of 5", ChatLog.findCount(2, 5))
    }

    @Test
    fun `the search words are the desktop's`() {
        assertEquals("Search what was said…", ChatLog.SEARCH_PLACEHOLDER)
        assertEquals(
            "Searched on your PC, in your kept chats only. Nothing is saved and nothing is sent to the AI.",
            ChatLog.SEARCH_NOTE,
        )
        assertEquals("No kept conversation has all of those words.", ChatLog.SEARCH_NONE)
        assertEquals("Not in this chat.", ChatLog.FIND_NONE)
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
                   {"role":"user","text":"look it up","at":1790000010,"provenance":"voice","read_outside":true,"answer_kept":false},
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
        // Only the PC's "false" says the answer was not kept; missing is kept (an older PC).
        assertEquals(listOf(true, true, true, false), t.turns.map { it.answerKept })
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
        // The desktop asks the same sentence (one wording for both apps).
        assertEquals(
            "Delete every conversation older than 30 days from your PC now, and from then on? " +
                "This cannot be undone.",
            ChatLog.keepConfirm(30),
        )
        assertEquals(
            "Delete every conversation older than 1 year from your PC now, and from then on? " +
                "This cannot be undone.",
            ChatLog.keepConfirm(365),
        )
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
        assertEquals("Sat 12 Sep 12:00", ChatLog.whenLine(noon - 12 * 86_400, zone, today))
        assertEquals("Fri 3 Jan 2025", ChatLog.whenLine(LocalDate.of(2025, 1, 3).atStartOfDay(zone).toEpochSecond(), zone, today))
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

    // ------------------------------------- facts this chat taught (s. 79) ---

    @Test
    fun `only a real conversation id asks for the facts it taught`() {
        assertEquals(
            "/api/memory/conversation-facts?conversation_id=conv-abc_123",
            ChatLog.factsPath("conv-abc_123"),
        )
        for (bad in listOf("", "short", "has space in it", "a&b=c-defgh", "x".repeat(65))) {
            assertNull(bad, ChatLog.factsPath(bad))
        }
    }

    @Test
    fun `the facts a chat taught are read, and anything odd is left out`() {
        val t = ChatLog.taught(
            obj(
                """
                {"conversation_id": "conv-abc_123", "facts": [
                  {"id": 41, "text": " Owner's passport is in the top drawer ", "created": 1790000000},
                  {"id": 0, "text": "no id"}, {"id": "42", "text": "id is a string"},
                  {"id": 43, "text": "   "}, {"text": "no id at all"},
                  {"id": 44, "text": "Owner likes green tea"}],
                 "count": 2, "more": false}
                """.trimIndent(),
            ),
        )
        assertTrue(t.available)
        assertEquals(listOf(41L, 44L), t.facts.map { it.id })
        assertEquals("Owner's passport is in the top drawer", t.facts[0].text)
        assertEquals(0, t.hiddenCount)
        val hidden = ChatLog.taught(obj("""{"facts": [], "hidden": true, "hidden_count": 2}"""))
        assertEquals(2, hidden.hiddenCount)
        assertTrue(hidden.facts.isEmpty())
    }

    @Test
    fun `deleting a chat names how many facts go, and none is ticked by the words`() {
        assertEquals("Delete the chat", ChatLog.deleteChatButton(0))
        assertEquals("Delete the chat and forget 1 fact", ChatLog.deleteChatButton(1))
        assertEquals("Delete the chat and forget 3 facts", ChatLog.deleteChatButton(3))
        assertTrue(
            ChatLog.chatFactsIntro(1)
                .startsWith("Jarvis learned 1 fact from this chat. It is kept unless you tick it"),
        )
        assertTrue(
            ChatLog.chatFactsIntro(2)
                .startsWith("Jarvis learned 2 facts from this chat. They are kept unless you tick them"),
        )
        assertTrue(ChatLog.deleteAndForgetConfirm(0).endsWith("The facts it taught are kept."))
        assertTrue(ChatLog.deleteAndForgetConfirm(2).startsWith("Delete this conversation and forget 2 facts?"))
        assertTrue(ChatLog.chatFactsHiddenLine(2).contains("Your memory lists are hidden, so they are kept."))
        assertEquals("Deleted from your PC.", ChatLog.deleteDoneWords("Deleted from your PC.", 0, 0))
        assertEquals(
            "Deleted from your PC. Forgot 2 facts. 1 fact could not be forgotten - try Forget on it in the Brain.",
            ChatLog.deleteDoneWords("Deleted from your PC.", 2, 1),
        )
    }
}
