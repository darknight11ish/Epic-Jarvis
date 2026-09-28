package com.jarvis.client

import com.jarvis.client.net.ChatHistory
import com.jarvis.client.net.ChatLog
import com.jarvis.client.net.ForgetRange
import com.jarvis.client.net.MemoryErase
import com.jarvis.client.net.Projects
import com.jarvis.client.net.TemporaryChat
import kotlinx.serialization.json.Json
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.jsonArray
import kotlinx.serialization.json.jsonObject
import kotlinx.serialization.json.jsonPrimitive
import kotlinx.serialization.json.long
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test
import java.io.File
import java.time.Instant
import java.time.ZoneOffset

/**
 * History and the chat on Home, after the chat audit (the owner's decisions
 * of 2026-09-28, "Chats, after the chat audit" and "History marks Live
 * sessions"), held to the words and worked examples both apps share.
 *
 * `contract/history-cases.json` is written by tools/gen_history_cases.py -
 * byte for byte the file the desktop's tests/history.mjs reads - so a
 * sentence changed in one app and not the other fails here or there.
 */
class HistoryContractTest {

    private val doc: JsonObject = run {
        val text = requireNotNull(javaClass.classLoader?.getResource("contract/history-cases.json")) {
            "contract/history-cases.json is missing - run tools/gen_history_cases.py"
        }.readText()
        Json.parseToJsonElement(text) as JsonObject
    }
    private val words = doc["words"]!!.jsonObject
    private fun w(key: String): String = words[key]!!.jsonPrimitive.content
    private fun map(key: String): Map<String, String> =
        words[key]!!.jsonObject.mapValues { it.value.jsonPrimitive.content }

    @Test
    fun `History's words are the desktop's, word for word`() {
        assertEquals(doc["kinds"]!!.jsonArray.map { it.jsonPrimitive.content }, ChatLog.KINDS)
        assertEquals(doc["continuable"]!!.jsonArray.map { it.jsonPrimitive.content }, ChatLog.CONTINUABLE)
        assertEquals(map("kind_tag"), ChatLog.KIND_TAG)
        assertEquals(map("kind_title"), ChatLog.KIND_TITLE)
        assertEquals(
            words["filters"]!!.jsonArray.map { it.jsonArray[0].jsonPrimitive.content to it.jsonArray[1].jsonPrimitive.content },
            ChatLog.FILTERS,
        )
        assertEquals(w("filter_label"), ChatLog.FILTER_LABEL)
        assertEquals(w("filter_none"), ChatLog.FILTER_NONE)
        assertEquals(map("chatbot_who"), ChatLog.CHATBOT_WHO)
        assertEquals(w("continue"), ChatLog.CONTINUE)
        assertEquals(w("continue_title_phone"), ChatLog.CONTINUE_TITLE)
        assertEquals(map("continue_why"), ChatLog.CONTINUE_WHY)
        assertEquals(w("copy"), ChatLog.COPY)
        assertEquals(w("copy_title"), ChatLog.COPY_TITLE)
        assertEquals(w("copied"), ChatLog.COPIED)
        assertEquals(w("forget_range_link"), ChatLog.FORGET_RANGE_LINK)
        assertEquals(w("forget_range_link_title"), ChatLog.FORGET_RANGE_LINK_TITLE)
        assertEquals(w("delete_keeps_facts"), ChatLog.DELETE_KEEPS_FACTS)
        assertEquals(w("delete_support"), ChatLog.DELETE_SUPPORT)
        assertEquals(w("keep_support_note"), ChatLog.KEEP_SUPPORT_NOTE)
        assertEquals(w("no_title"), ChatLog.NO_TITLE)
        assertEquals(w("search_label"), ChatLog.SEARCH_LABEL)
        assertEquals(w("no_title_match"), ChatLog.NO_MATCH)
        assertEquals(w("no_title_match_more"), ChatLog.NO_MATCH_MORE)
        assertEquals(w("history_settings"), ChatLog.HISTORY_SETTINGS)
        assertEquals(w("history_settings_title"), ChatLog.HISTORY_SETTINGS_TITLE)
        assertEquals(w("messages_one"), ChatLog.messagesWords(1))
        assertEquals(w("messages_many").replace("{n}", "7"), ChatLog.messagesWords(7))
    }

    @Test
    fun `Home's words for the chat it is in are the Jarvis bar's`() {
        assertEquals(w("earlier_chats"), ChatHistory.EARLIER_CHATS)
        assertEquals(w("earlier_chats_title"), ChatHistory.EARLIER_CHATS_TITLE)
        assertEquals(w("idle_new"), ChatHistory.IDLE_NEW_LINE)
        assertEquals(w("new_conversation"), ChatHistory.NEW_CONVERSATION)
        assertEquals(w("chat_gone"), ChatHistory.CHAT_GONE)
        assertEquals(w("moved_here"), ChatHistory.MOVED_HERE)
        assertEquals(w("continued_trimmed"), ChatHistory.CONTINUED_TRIMMED)
        assertEquals(w("continued_tainted"), ChatHistory.CONTINUED_TAINTED)
        assertEquals(w("continued_nothing"), ChatHistory.CONTINUED_NOTHING)
        assertEquals(w("continued_temporary_off"), ChatHistory.CONTINUED_TEMPORARY_OFF)
        assertEquals(w("continue_busy"), ChatHistory.CONTINUE_BUSY)
        assertEquals(w("continued").replace("{title}", "Dentist"), ChatHistory.continuedLine("Dentist"))
        assertEquals(w("thread_one"), ChatHistory.threadSummary(1))
        assertEquals(w("thread_many").replace("{n}", "3"), ChatHistory.threadSummary(3))
        assertEquals(doc["idle_ms"]!!.jsonPrimitive.long, ChatHistory.IDLE_NEW_MS)
        assertEquals(doc["max_exchanges"]!!.jsonPrimitive.content.toInt(), ChatHistory.MAX_EXCHANGES)
        assertEquals(doc["max_chars"]!!.jsonPrimitive.content.toInt(), ChatHistory.MAX_CHARS)
    }

    @Test
    fun `the other screens' new sentences are the desktop's too`() {
        assertEquals(w("game_temporary"), TemporaryChat.GAME)
        assertEquals(w("erased_no_chat"), MemoryErase.ERASED_NO_CHAT)
        assertEquals(
            w("erase_chat_named").replace("{title}", "Dentist").replace("{when}", "Today 14:05"),
            MemoryErase.chatNamed("Dentist", "Today 14:05"),
        )
        assertEquals(
            "In your own words. " + w("project_chats_later"),
            Projects.WORDS["instructions_under"],
        )
        assertEquals("Support chat", ForgetRange.chatKindTag("support"))
        assertEquals(null, ForgetRange.chatKindTag("chat"))
    }

    @Test
    fun `dates, a Live session's line and messages follow the worked examples`() {
        val zone = ZoneOffset.UTC
        val today = Instant.ofEpochSecond(doc["today"]!!.jsonPrimitive.long).atZone(zone).toLocalDate()
        for (c in doc["when_cases"]!!.jsonArray.map { it.jsonObject }) {
            assertEquals(c.toString(), c["expect"]!!.jsonPrimitive.content,
                ChatLog.whenLine(c["at"]!!.jsonPrimitive.long, zone, today))
        }
        for (c in doc["live_cases"]!!.jsonArray.map { it.jsonObject }) {
            assertEquals(c.toString(), c["expect"]!!.jsonPrimitive.content,
                ChatLog.liveLine(c["started"]!!.jsonPrimitive.long, c["updated"]!!.jsonPrimitive.long, zone, today))
        }
        for (c in doc["messages_cases"]!!.jsonArray.map { it.jsonObject }) {
            assertEquals(c["expect"]!!.jsonPrimitive.content,
                ChatLog.messagesWords(c["n"]!!.jsonPrimitive.content.toInt()))
        }
    }

    @Test
    fun `an old answer loses its markdown marks the way the examples say`() {
        for (c in doc["plain_cases"]!!.jsonArray.map { it.jsonObject }) {
            assertEquals(c["in"]!!.jsonPrimitive.content, c["out"]!!.jsonPrimitive.content,
                ChatLog.plainAnswer(c["in"]!!.jsonPrimitive.content))
        }
    }

    @Test
    fun `Continue this chat loads what the worked examples load`() {
        for (c in doc["continue_cases"]!!.jsonArray.map { it.jsonObject }) {
            val name = c["name"]!!.jsonPrimitive.content
            val turns = c["turns"]!!.jsonArray.map { it.jsonObject }.map { t ->
                ChatLog.Turn(
                    role = t["role"]!!.jsonPrimitive.content,
                    text = t["text"]!!.jsonPrimitive.content,
                    at = null,
                    provenance = t["provenance"]?.jsonPrimitive?.content,
                    readOutside = false,
                    answerKept = t["answer_kept"]?.jsonPrimitive?.content != "false",
                )
            }
            val (window, trimmed) = ChatHistory.continueWindow(turns)
            val want = c["window"]!!.jsonArray.map { it.jsonObject }.map { x ->
                Triple(
                    x["question"]!!.jsonPrimitive.content,
                    x["answer"]!!.jsonPrimitive.content,
                    // No tag in the example (an odd one is dropped): the
                    // phone sends it as "unknown", never the odd word.
                    (x["provenance"] as? kotlinx.serialization.json.JsonPrimitive)
                        ?.takeIf { it.isString }?.content ?: "unknown",
                )
            }
            assertEquals(name, want, window.map { Triple(it.question, it.answer, it.asked.last().provenance) })
            assertEquals(name, c["trimmed"]!!.jsonPrimitive.content == "true", trimmed)
        }
    }

    @Test
    fun `an opened record says whether it can be carried on, and why not`() {
        fun transcript(kind: String?, vararg roles: String): ChatLog.Transcript {
            val body = buildString {
                append("{\"id\":\"conv-00000001\",\"title\":\"t\"")
                if (kind != null) append(",\"kind\":\"$kind\"")
                append(",\"turns\":[")
                append(roles.joinToString(",") { "{\"role\":\"$it\",\"text\":\"x\"}" })
                append("]}")
            }
            return requireNotNull(ChatLog.transcript(Json.parseToJsonElement(body) as JsonObject))
        }
        assertTrue(transcript("chat", "user", "assistant").continuable)
        assertTrue(transcript("live", "user", "assistant").continuable)
        assertTrue("an older PC's chat", transcript(null, "user", "assistant").continuable)
        for (kind in listOf("support", "chatbot", "compare")) {
            val t = transcript(kind)
            assertFalse(kind, t.continuable)
            assertEquals(kind, ChatLog.CONTINUE_WHY[kind], t.continueWhy)
        }
        assertFalse("an older PC's support record", transcript(null, "support").continuable)
    }

    @Test
    fun `the thread shows every finished pair, and not the one on screen twice`() {
        val one = listOf(ChatHistory.UserTurn("hi", "typed"))
        val two = listOf(ChatHistory.UserTurn("and then?", "typed"))
        var thread = ChatHistory.addToThread(emptyList(), one, "Hello.")
        thread = ChatHistory.addToThread(thread, two, "Then this.")
        assertEquals(listOf("hi"), ChatHistory.threadBefore(thread, "and then?", streaming = false).map { it.question })
        assertEquals(2, ChatHistory.threadBefore(thread, "a new one", streaming = true).size)
        // Past the model's re-send window, the thread keeps going (only capped).
        var long = emptyList<ChatHistory.Exchange>()
        repeat(ChatHistory.MAX_EXCHANGES + 5) { long = ChatHistory.addToThread(long, one, "Hello.") }
        assertEquals(ChatHistory.MAX_EXCHANGES + 5, long.size)
        repeat(ChatHistory.THREAD_MAX) { long = ChatHistory.addToThread(long, one, "Hello.") }
        assertEquals(ChatHistory.THREAD_MAX, long.size)
        assertEquals("a blank answer is not a pair", long, ChatHistory.addToThread(long, one, " "))
    }

    @Test
    fun `a new conversation after 30 quiet minutes, never mid-chat or with nothing said`() {
        val t0 = 1_800_000_000_000L
        val idle = ChatHistory.IDLE_NEW_MS
        assertFalse(ChatHistory.idleExpired(t0, t0 + idle - 1, hasConversation = true))
        assertTrue(ChatHistory.idleExpired(t0, t0 + idle, hasConversation = true))
        assertFalse("nothing to end", ChatHistory.idleExpired(t0, t0 + idle * 3, hasConversation = false))
        assertFalse("no answer yet", ChatHistory.idleExpired(0, t0, hasConversation = true))
    }

    @Test
    fun `the phone's wiring holds the rules`() {
        val main = "jarvis-client/app/src/main/java/com/jarvis/client"
        val session = repoFile("$main/net/ChatSession.kt").readText()
        val send = session.substring(session.indexOf("suspend fun send("))
        // The 30-minute rule runs before the question is built, and never in Live.
        assertTrue(send.indexOf("idleExpired") in 0 until send.indexOf("val earlier = _history.value"))
        assertTrue(send.contains("if (!live && ChatHistory.idleExpired("))
        val runtime = repoFile("$main/JarvisRuntime.kt").readText()
        // Deleting the chat Home is in starts a new one, from every path.
        val delete = runtime.substring(runtime.indexOf("suspend fun deleteHistory("))
        assertTrue(delete.substring(0, 600).contains("chatsGone(listOf(id))"))
        val erase = runtime.substring(runtime.indexOf("suspend fun eraseAutoFact("))
        assertTrue(erase.substring(0, 1600).contains("chatsGone(listOf(chatId))"))
        assertTrue(runtime.contains("if (outcome == \"done\") chatsGone(pending)"))
        // "Move it here" carries on the session's own chat, named by the PC.
        val start = runtime.substring(runtime.indexOf("suspend fun liveStart("))
        assertTrue(start.substring(0, 2500).contains("get(\"conversation_id\")"))
        assertTrue(start.substring(0, 3000).contains("rules.startBody(cid)"))
        val live = repoFile("$main/ui/screens/LiveScreen.kt").readText()
        assertTrue(live.contains("JarvisRuntime.liveStart(move = true)"))
        // Continue is never offered for what cannot be carried on.
        val history = repoFile("$main/ui/screens/HistoryScreen.kt").readText()
        assertTrue(history.contains("if (t.continuable) {"))
        assertFalse("the search words stay out of saved state", history.contains("var search by rememberSaveable"))
        // The forms that sat in Brain's scrolling list keep what was typed.
        for (f in listOf("ForgetRangePlate.kt", "ChatbotPlate.kt")) {
            val src = repoFile("$main/ui/screens/$f").readText()
            assertTrue(f, src.contains("rememberSaveable"))
        }
    }

    /** A file of this repository, found from wherever the tests run. */
    private fun repoFile(rel: String): File {
        var dir: File? = File(System.getProperty("user.dir") ?: ".").absoluteFile
        while (dir != null) {
            val f = File(dir, rel)
            if (f.isFile) return f
            dir = dir.parentFile
        }
        error("$rel not found above ${System.getProperty("user.dir")}")
    }
}
