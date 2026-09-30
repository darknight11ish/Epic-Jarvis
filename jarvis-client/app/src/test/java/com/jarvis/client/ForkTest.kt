package com.jarvis.client

import com.jarvis.client.net.ChatFork
import com.jarvis.client.net.ChatLog
import com.jarvis.client.net.JarvisJson
import kotlinx.serialization.json.Json
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.jsonArray
import kotlinx.serialization.json.jsonObject
import kotlinx.serialization.json.jsonPrimitive
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNotNull
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test

/**
 * "Fork from here" on the phone (docs/JARVIS-API.md section 110; the frozen
 * "Fork contract" in docs/CHAT-TAGS-DESIGN.md), held to the words and worked
 * cases in contract/history-cases.json - byte for byte the file the
 * desktop's tests read.
 */
class ForkTest {

    private val doc: JsonObject = run {
        val text = requireNotNull(javaClass.classLoader?.getResource("contract/history-cases.json")) {
            "contract/history-cases.json is missing - run tools/gen_history_cases.py"
        }.readText()
        Json.parseToJsonElement(text) as JsonObject
    }
    private val words = doc["words"]!!.jsonObject
    private fun w(key: String): String = words[key]!!.jsonPrimitive.content

    private fun obj(json: String): JsonObject = JarvisJson.parseToJsonElement(json).jsonObject

    private val newId = "0b7e1c2a-3d4f-4a5b-8c6d-7e8f9a0b1c2d"

    @Test
    fun `the words are the fixture's, word for word`() {
        assertEquals(w("fork"), ChatFork.BUTTON)
        assertEquals(w("fork_title"), ChatFork.TITLE)
        assertEquals(w("fork_label_user"), ChatFork.LABEL_USER)
        assertEquals(w("fork_label_assistant"), ChatFork.LABEL_ASSISTANT)
        assertEquals(w("fork_busy"), ChatFork.BUSY)
        assertEquals(w("fork_no"), ChatFork.NO)
        assertEquals(w("fork_error_fallback"), ChatFork.ERROR_FALLBACK)
        val errors = words["fork_errors"]!!.jsonObject.mapValues { it.value.jsonPrimitive.content }
        assertEquals(errors, ChatFork.ERRORS)
        val labels = doc["fork_labels"]!!.jsonObject
        assertEquals(labels["user"]!!.jsonPrimitive.content, ChatFork.label("user"))
        assertEquals(labels["assistant"]!!.jsonPrimitive.content, ChatFork.label("assistant"))
    }

    @Test
    fun `each screen-reader name holds the visible words`() {
        assertTrue(ChatFork.label("user").contains(ChatFork.BUTTON))
        assertTrue(ChatFork.label("assistant").contains(ChatFork.BUTTON))
    }

    @Test
    fun `the title's prefix and length are the fixture's, and the phone never builds a title`() {
        assertEquals(doc["fork_prefix"]!!.jsonPrimitive.content, ChatFork.PREFIX)
        assertEquals(doc["fork_title_max"]!!.jsonPrimitive.content.toInt(), ChatFork.TITLE_MAX)
        assertEquals(ChatFork.PREFIX + "{title}", w("fork_title_of"))
        // The success line shows the title exactly as the PC sent it.
        val sent = ChatFork.PREFIX + "Dentist on Tuesday"
        assertEquals(w("fork_done").replace("{title}", sent), ChatFork.done(sent))
        val r = ChatFork.result(obj("""{"ok":true,"id":"$newId","title":"$sent","turns":4,"tag_id":2}"""))
        assertTrue(r.ok)
        assertEquals(newId, r.id)
        assertEquals(sent, r.title)
        assertEquals(4, r.turns)
        assertEquals(2, r.tagId)
        assertEquals(w("fork_done").replace("{title}", sent), r.said)
        // No tag: null, not 0.
        assertNull(ChatFork.result(obj("""{"ok":true,"id":"$newId","title":"t","turns":1,"tag_id":null}""")).tagId)
    }

    @Test
    fun `refusal sentences follow the fixture's worked cases`() {
        for (el in doc["fork_error_cases"]!!.jsonArray) {
            val c = el.jsonObject
            val a = c["answer"]!!.jsonObject
            val r = ChatFork.result(a)
            assertFalse(a.toString(), r.ok)
            assertNull(r.id)
            assertEquals(a.toString(), c["expect"]!!.jsonPrimitive.content, r.said)
            val code = a["error"]?.jsonPrimitive?.content
            val message = a["message"]?.jsonPrimitive?.content
            assertEquals(a.toString(), c["expect"]!!.jsonPrimitive.content, ChatFork.errorSentence(code, message))
        }
        // The two why-lines are what the PC sends as `message` on not_forkable.
        assertEquals(w("fork_why_crisis"), ChatFork.errorSentence("not_forkable", w("fork_why_crisis")))
        assertEquals(w("fork_why_kind"), ChatFork.errorSentence("not_forkable", w("fork_why_kind")))
        // Unknown code, blank message: the fallback.
        assertEquals(ChatFork.ERROR_FALLBACK, ChatFork.errorSentence("teapot", "  "))
        assertEquals(ChatFork.ERROR_FALLBACK, ChatFork.errorSentence(null, null))
    }

    @Test
    fun `an ok answer with no usable id is not a fork to open`() {
        assertFalse(ChatFork.result(obj("""{"ok":true,"title":"x"}""")).ok)
        assertFalse(ChatFork.result(obj("""{"ok":true,"id":"../etc","title":"x"}""")).ok)
        assertEquals(ChatFork.ERROR_FALLBACK, ChatFork.result(obj("""{"ok":true,"id":7}""")).said)
        assertEquals(ChatFork.ERROR_FALLBACK, ChatFork.result(null).said)
    }

    @Test
    fun `the request is exactly id and upto`() {
        val b = obj(ChatFork.body("abc-12345678", 3))
        assertEquals(setOf("id", "upto"), b.keys)
        assertEquals("abc-12345678", b["id"]!!.jsonPrimitive.content)
        assertEquals(3, b["upto"]!!.jsonPrimitive.content.toInt())
        assertEquals("/api/history/fork", ChatFork.FORK_PATH)
    }

    @Test
    fun `the button is offered on user messages and kept answers of a forkable chat, only`() {
        assertTrue(ChatFork.offered(true, "user", 0))
        assertTrue(ChatFork.offered(true, "assistant", 5))
        assertFalse(ChatFork.offered(false, "user", 0))
        assertFalse(ChatFork.offered(true, "support", 1))
        assertFalse(ChatFork.offered(true, "chatbot", 1))
        assertFalse(ChatFork.offered(true, "user", null))
        assertFalse(ChatFork.offered(true, "user", -1))
    }

    @Test
    fun `an opened chat reads idx, forkable and fork_why, and ignores unknown keys`() {
        val t = ChatLog.transcript(
            obj(
                """{"id":"chat-0001","title":"Dentist","forkable":true,"fork_why":"","brand_new_key":{"a":1},
                   "turns":[
                     {"idx":0,"role":"user","text":"hi","future":true},
                     {"idx":1,"role":"assistant","text":"hello"},
                     {"idx":"2","role":"user","text":"idx as text is not a number"},
                     {"idx":-4,"role":"user","text":"negative"},
                     {"role":"user","text":"no idx"}
                   ]}""",
            ),
        )
        assertNotNull(t)
        t!!
        assertTrue(t.forkable)
        assertNull(t.forkWhy)
        assertEquals(listOf(0, 1, null, null, null), t.turns.map { it.idx })
    }

    @Test
    fun `a chat that cannot be forked carries the PC's reason, else the plain one`() {
        val why = w("fork_why_crisis")
        val a = ChatLog.transcript(obj("""{"id":"chat-0001","forkable":false,"fork_why":"$why","turns":[]}"""))!!
        assertFalse(a.forkable)
        assertEquals(why, a.forkWhy)
        val b = ChatLog.transcript(obj("""{"id":"chat-0001","forkable":false,"turns":[]}"""))!!
        assertEquals(w("fork_no"), b.forkWhy)
        val c = ChatLog.transcript(obj("""{"id":"chat-0001","forkable":false,"fork_why":"   ","turns":[]}"""))!!
        assertEquals(w("fork_no"), c.forkWhy)
    }

    @Test
    fun `an older PC sends neither: no buttons and no reason line`() {
        val t = ChatLog.transcript(obj("""{"id":"chat-0001","turns":[{"role":"user","text":"hi"}]}"""))!!
        assertFalse(t.forkable)
        assertNull(t.forkWhy)
        assertNull(t.turns[0].idx)
        assertFalse(ChatFork.offered(t.forkable, t.turns[0].role, t.turns[0].idx))
        // A non-boolean flag is not a yes.
        val odd = ChatLog.transcript(obj("""{"id":"chat-0001","forkable":"true","turns":[]}"""))!!
        assertFalse(odd.forkable)
        assertNull(odd.forkWhy)
    }
}
