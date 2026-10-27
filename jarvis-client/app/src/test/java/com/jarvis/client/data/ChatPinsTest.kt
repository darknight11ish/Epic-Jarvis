package com.jarvis.client.data

import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNotEquals
import org.junit.Assert.assertSame
import org.junit.Assert.assertTrue
import org.junit.Test

/**
 * The phone's own pinned chat messages (the owner's request of 2026-10-27: "a
 * pin message button that pins the message and remembers it and can be found
 * easily in a new menu").
 *
 * Everything here is JVM-only: [ChatPins] is pure Kotlin on purpose, so the
 * rules that matter - one pin per message, newest first, a cap that refuses
 * instead of dropping an older pin, a corrupt file that costs only the rows it
 * damaged, and ages that never read backwards - are proved without a phone,
 * an emulator or a Gradle Android build. The thin SharedPreferences wrapper
 * ([PinnedChatStore]) is not exercised here; it does nothing this object does
 * not do.
 */
class ChatPinsTest {

    private val chat = "0b7e1c2a-3d4f-4a5b-8c6d-7e8f9a0b1c2d"
    private val otherChat = "11111111-2222-4333-8444-555555555555"
    private val question = "What is wrong with my boiler?"
    private val now = 1_790_000_000_000L

    private fun one(
        text: String = "The boiler's pressure is low.",
        at: Long = now,
        chatId: String = chat,
        label: String = question,
    ): List<PinnedMessage> = ChatPins.pin(emptyList(), chatId, label, text, at)

    // ---- Pinning ------------------------------------------------------------

    @Test
    fun `nothing is pinned on a fresh phone`() {
        assertTrue(ChatPins.fromJson(null).isEmpty())
        assertTrue(ChatPins.fromJson("").isEmpty())
        assertFalse(ChatPins.full(emptyList()))
        // The screen's own words are there for the empty list.
        assertTrue(ChatPins.EMPTY.isNotEmpty())
        assertTrue(ChatPins.EMPTY.contains(ChatPins.PIN))
    }

    @Test
    fun `a pin keeps the words, which chat and when`() {
        val rows = one()
        assertEquals(1, rows.size)
        val row = rows.single()
        assertEquals("The boiler's pressure is low.", row.text)
        assertEquals(chat, row.chatId)
        assertEquals(question, row.chatLabel)
        assertEquals(now, row.atMs)
        // The row is a pin of that message, in that chat, and nothing else.
        assertEquals(ChatPins.key(chat, "The boiler's pressure is low."), row.key)
        assertTrue(ChatPins.has(rows, chat, "The boiler's pressure is low."))
    }

    @Test
    fun `blank words are never a pin`() {
        assertSame(emptyList<PinnedMessage>(), ChatPins.pin(emptyList(), chat, "", "   ", now))
        // A list that already has rows is handed back untouched, too.
        val rows = one()
        assertSame(rows, ChatPins.pin(rows, chat, question, "\n\n  \t ", now + 1))
    }

    @Test
    fun `newest first, and that is the order a restart brings back`() {
        var rows = ChatPins.pin(emptyList(), chat, question, "First answer.", now)
        rows = ChatPins.pin(rows, chat, question, "Second answer.", now + 1_000)
        rows = ChatPins.pin(rows, chat, question, "Third answer.", now + 2_000)
        assertEquals(
            listOf("Third answer.", "Second answer.", "First answer."),
            rows.map { it.text },
        )
        // ...and the same order after the file is read back.
        assertEquals(rows.map { it.key }, ChatPins.fromJson(ChatPins.toJson(rows)).map { it.key })
    }

    @Test
    fun `one message is one pin however it was reached`() {
        val rows = one("One answer.")
        // Pinning the same words again - from the answer on screen, or from the
        // same answer once it has moved into the thread - changes nothing.
        assertSame(rows, ChatPins.pin(rows, chat, question, "One answer.", now + 5_000))
        // Even with the whitespace the thread keeps instead of the answer's own.
        assertSame(rows, ChatPins.pin(rows, chat, question, "  One\n\nanswer. ", now + 9_000))
        assertEquals(1, rows.size)
    }

    @Test
    fun `the cap refuses rather than dropping the oldest`() {
        var rows = emptyList<PinnedMessage>()
        for (i in 0 until ChatPins.CAP) {
            rows = ChatPins.pin(rows, chat, question, "Answer number $i.", now + i)
        }
        assertEquals(ChatPins.CAP, rows.size)
        assertTrue(ChatPins.full(rows))
        // The oldest is still here: nothing was quietly thrown away to make room.
        assertTrue(rows.any { it.text == "Answer number 0." })
        // One more is refused, and the list comes back as the same list.
        val refused = ChatPins.pin(rows, chat, question, "One too many.", now + 10_000)
        assertSame(rows, refused)
        assertEquals(ChatPins.CAP, refused.size)
        // Unpinning makes room again.
        val roomAgain = ChatPins.unpin(rows, rows.first().key)
        assertFalse(ChatPins.full(roomAgain))
        assertEquals(ChatPins.CAP, ChatPins.pin(roomAgain, chat, question, "One too many.", now + 10_000).size)
    }

    @Test
    fun `the full sentence says the cap and what to do`() {
        assertTrue(ChatPins.full().contains(ChatPins.CAP.toString()))
        assertTrue(ChatPins.full().contains("Unpin"))
    }

    @Test
    fun `a message longer than the cap is cut and marked`() {
        val long = "a".repeat(ChatPins.MAX_TEXT + 500)
        val row = one(long).single()
        assertEquals(ChatPins.MAX_TEXT + 1, row.text.length)
        assertTrue(row.text.endsWith("…"))
        assertEquals(long.take(ChatPins.MAX_TEXT), row.text.dropLast(1))
    }

    @Test
    fun `unpin takes one out and nothing else`() {
        var rows = one("Kept answer.")
        rows = ChatPins.pin(rows, chat, question, "Removed answer.", now + 1_000)
        val removed = rows.first { it.text == "Removed answer." }
        val after = ChatPins.unpin(rows, removed.key)
        assertEquals(listOf("Kept answer."), after.map { it.text })
        // Unpinning something that is not there changes nothing.
        assertSame(after, ChatPins.unpin(after, removed.key))
        assertSame(after, ChatPins.unpin(after, "not-a-key"))
    }

    // ---- Identity -----------------------------------------------------------

    @Test
    fun `a key belongs to one chat and one message`() {
        val a = ChatPins.key(chat, "Same words.")
        assertEquals(a, ChatPins.key(chat, "Same words."))
        assertEquals(a, ChatPins.key(chat, "  Same\n\nwords.  "))
        assertNotEquals(a, ChatPins.key(otherChat, "Same words."))
        assertNotEquals(a, ChatPins.key(chat, "Different words."))
        // The chat id leads, so two chats can never be confused by eye either.
        assertTrue(a.startsWith("$chat#"))
        assertEquals(chat.length + 1 + 16, a.length)
        // Blank words still make a key (nothing is pinned with it - [pin] refuses).
        assertTrue(ChatPins.key(chat, "").startsWith("$chat#"))
    }

    // ---- Kept on disk -------------------------------------------------------

    @Test
    fun `the file round trips every field`() {
        var rows = ChatPins.pin(emptyList(), chat, question, "First answer.", now)
        rows = ChatPins.pin(rows, otherChat, "", "An answer from a chat nobody kept.", now + 1_000)
        val back = ChatPins.fromJson(ChatPins.toJson(rows))
        assertEquals(rows, back)
        // Newest first, whatever order the file happened to be in.
        assertEquals(rows.first().text, back.first().text)
    }

    @Test
    fun `a corrupt file costs only the rows it damaged`() {
        assertTrue(ChatPins.fromJson("not json at all").isEmpty())
        assertTrue(ChatPins.fromJson("""{"pins":[]}""").isEmpty())
        assertTrue(ChatPins.fromJson("[]").isEmpty())
        val mixed = """
            [
              {"key":"$chat#1111111111111111","text":"Good one.","chat_id":"$chat",
               "chat_label":"$question","at_ms":$now},
              {"key":"only-a-key"},
              {"text":"no key at all","at_ms":$now},
              {"key":"k2","text":"","at_ms":$now},
              "a string is not a row",
              {"key":"$chat#2222222222222222","text":"Good two.","chat_id":"$chat",
               "chat_label":"$question","at_ms":${now + 1}}
            ]
        """.trimIndent()
        val rows = ChatPins.fromJson(mixed)
        assertEquals(listOf("Good two.", "Good one."), rows.map { it.text })
        // A missing chat or label reads as "not kept", never as a crash.
        val bare = ChatPins.fromJson("""[{"key":"k","text":"Kept words.","at_ms":1}]""")
        assertEquals("", bare.single().chatId)
        assertEquals("", bare.single().chatLabel)
        // A duplicate key collapses to one row.
        val dup = ChatPins.fromJson(
            """[{"key":"k","text":"One.","at_ms":1},{"key":"k","text":"Two.","at_ms":2}]""",
        )
        assertEquals(1, dup.size)
    }

    // ---- What a row says ----------------------------------------------------

    @Test
    fun `ages read in plain words and never go backwards`() {
        assertEquals("just now", ChatPins.ageLine(now, now))
        assertEquals("just now", ChatPins.ageLine(now, now + 59_999))
        // A clock corrected backwards is not "-3 minutes ago".
        assertEquals("just now", ChatPins.ageLine(now, now - 300_000))
        assertEquals("1 minute ago", ChatPins.ageLine(now, now + 60_000))
        assertEquals("5 minutes ago", ChatPins.ageLine(now, now + 5 * 60_000))
        assertEquals("1 hour ago", ChatPins.ageLine(now, now + 3_600_000))
        assertEquals("2 hours ago", ChatPins.ageLine(now, now + 2 * 3_600_000L))
        assertEquals("1 day ago", ChatPins.ageLine(now, now + 86_400_000))
        assertEquals("6 days ago", ChatPins.ageLine(now, now + 6 * 86_400_000L))
        assertEquals("1 week ago", ChatPins.ageLine(now, now + 7 * 86_400_000L))
        assertEquals("4 weeks ago", ChatPins.ageLine(now, now + 30 * 86_400_000L))
        assertEquals("1 month ago", ChatPins.ageLine(now, now + 35 * 86_400_000L))
        assertEquals("11 months ago", ChatPins.ageLine(now, now + 350 * 86_400_000L))
        assertEquals("over a year ago", ChatPins.ageLine(now, now + 400 * 86_400_000L))
    }

    @Test
    fun `a row says which chat and when`() {
        val labelled = one().single()
        assertTrue(ChatPins.whereLine(labelled, now).startsWith(ChatPins.CHAT_PREFIX))
        assertTrue(ChatPins.whereLine(labelled, now).contains(question))
        assertTrue(ChatPins.whereLine(labelled, now).endsWith("just now"))
        val noLabel = ChatPins.pin(emptyList(), chat, "", "Words.", now).single()
        assertTrue(ChatPins.whereLine(noLabel, now).startsWith(ChatPins.CHAT_ON_PC))
        val noChat = ChatPins.pin(emptyList(), "", "", "Words.", now).single()
        assertTrue(ChatPins.whereLine(noChat, now).startsWith(ChatPins.CHAT_NOT_KEPT))
    }

    @Test
    fun `only a pin that came from a kept chat offers to open one`() {
        assertTrue(ChatPins.opens(one().single()))
        assertFalse(ChatPins.opens(ChatPins.pin(emptyList(), "", "", "Words.", now).single()))
    }

    @Test
    fun `a snippet is one line and says when it was cut`() {
        assertEquals("one two", ChatPins.snippet("  one\n\ntwo  "))
        assertEquals("Kept.", ChatPins.snippet("Kept.", max = 10))
        assertEquals("Kept…", ChatPins.snippet("Kept and more words.", max = 4))
        assertEquals("", ChatPins.snippet(""))
        // "Which chat" is the owner's question, one line, and no longer than asked.
        assertEquals("1 month of trouble", ChatPins.chatLabel("1 month\nof trouble"))
        assertTrue(ChatPins.chatLabel("q".repeat(500)).length <= ChatPins.MAX_LABEL + 1)
        assertEquals("", ChatPins.chatLabel(null))
    }

    @Test
    fun `the words a temporary chat is refused with name the reason`() {
        assertTrue(ChatPins.TEMPORARY.contains("Temporary"))
        // Nothing about it suggests anything was kept.
        assertFalse(ChatPins.TEMPORARY.contains("kept on this phone"))
    }
}
