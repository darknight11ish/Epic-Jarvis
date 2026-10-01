package com.jarvis.client

import com.jarvis.client.net.ChatLog
import com.jarvis.client.net.ChatMark
import com.jarvis.client.net.JarvisJson
import kotlinx.serialization.json.Json
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.int
import kotlinx.serialization.json.jsonArray
import kotlinx.serialization.json.jsonObject
import kotlinx.serialization.json.jsonPrimitive
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test

/**
 * "New section here" on the phone (docs/JARVIS-API.md section 106; the frozen
 * slice contract, section 9B of docs/OVERNIGHT-TAGS-DESIGN.md), held to the
 * words and worked cases in contract/history-cases.json - byte for byte the
 * file the desktop's tests read.
 */
class ChatMarkTest {

    private val doc: JsonObject = run {
        val text = requireNotNull(javaClass.classLoader?.getResource("contract/history-cases.json")) {
            "contract/history-cases.json is missing - run tools/gen_history_cases.py"
        }.readText()
        Json.parseToJsonElement(text) as JsonObject
    }
    private val words = doc["words"]!!.jsonObject
    private fun w(key: String): String = words[key]!!.jsonPrimitive.content

    private fun obj(json: String): JsonObject = JarvisJson.parseToJsonElement(json).jsonObject

    private val chat = "0b7e1c2a-3d4f-4a5b-8c6d-7e8f9a0b1c2d"

    @Test
    fun `the words are the fixture's, word for word`() {
        assertEquals(w("mark"), ChatMark.BUTTON)
        assertEquals(w("mark_label"), ChatMark.BUTTON_LABEL)
        assertEquals(w("mark_divider"), ChatMark.DIVIDER)
        assertEquals(w("mark_remove"), ChatMark.REMOVE)
        assertEquals(w("mark_done"), ChatMark.DONE)
        assertEquals(w("mark_removed"), ChatMark.REMOVED)
        assertEquals(w("mark_limit"), ChatMark.LIMIT)
        assertEquals(w("mark_no"), ChatMark.NO)
        assertEquals(w("mark_error_fallback"), ChatMark.ERROR_FALLBACK)
        val errors = words["mark_errors"]!!.jsonObject.mapValues { it.value.jsonPrimitive.content }
        assertEquals(errors, ChatMark.ERRORS)
        assertEquals(doc["mark_max"]!!.jsonPrimitive.int, ChatMark.MAX)
        assertEquals(doc["mark_min_turns"]!!.jsonPrimitive.int, ChatMark.MIN_TURNS)
    }

    @Test
    fun `the screen-reader name holds the visible words`() {
        assertTrue(ChatMark.BUTTON_LABEL.startsWith(ChatMark.BUTTON))
    }

    @Test
    fun `the request is exactly id, idx and on`() {
        val b = obj(ChatMark.body(chat, 12, true))
        assertEquals(setOf("id", "idx", "on"), b.keys)
        assertEquals(chat, b["id"]!!.jsonPrimitive.content)
        assertEquals(12, b["idx"]!!.jsonPrimitive.int)
        assertEquals("true", b["on"]!!.jsonPrimitive.content)
        assertEquals("false", obj(ChatMark.body(chat, 0, false))["on"]!!.jsonPrimitive.content)
    }

    @Test
    fun `every worked error case gives the fixture's sentence`() {
        val cases = doc["mark_error_cases"]!!.jsonArray
        assertTrue(cases.isNotEmpty())
        for (c in cases) {
            val o = c.jsonObject
            val answer = o["answer"]!!.jsonObject
            assertEquals("answer: $answer", o["expect"]!!.jsonPrimitive.content, ChatMark.result(answer, true).said)
            assertFalse(ChatMark.result(answer, true).ok)
        }
        // A body that is not readable is the fallback, never a crash.
        assertEquals(ChatMark.ERROR_FALLBACK, ChatMark.result(null, true).said)
    }

    @Test
    fun `every code the PC can name has a sentence`() {
        for (code in doc["mark_error_codes"]!!.jsonArray.map { it.jsonPrimitive.content }) {
            val said = ChatMark.errorSentence(code)
            assertTrue(code, said.isNotBlank())
            assertTrue(code, said != ChatMark.ERROR_FALLBACK)
        }
        assertEquals(ChatMark.ERROR_FALLBACK, ChatMark.errorSentence("something_new"))
    }

    @Test
    fun `a success reads the whole list and announces politely`() {
        val on = ChatMark.result(obj("""{"ok":true,"id":"$chat","idx":12,"on":true,"marks":[12,4]}"""), true)
        assertTrue(on.ok)
        assertEquals(ChatMark.DONE, on.said)
        assertEquals(setOf(4, 12), on.marks)
        val off = ChatMark.result(obj("""{"ok":true,"id":"$chat","idx":12,"on":false,"marks":[4]}"""), false)
        assertEquals(ChatMark.REMOVED, off.said)
        assertEquals(setOf(4), off.marks)
        // The answer's own `on` wins over what was asked.
        assertEquals(ChatMark.REMOVED, ChatMark.result(obj("""{"ok":true,"on":false,"marks":[]}"""), true).said)
        assertEquals(emptySet<Int>(), ChatMark.result(obj("""{"ok":true}"""), true).marks)
    }

    @Test
    fun `odd marks are ignored, never a crash`() {
        val m = ChatMark.marksOf(obj("""{"m":[3,"4",-1,2.5,null,true,7,7]}""")["m"])
        assertEquals(setOf(3, 7), m)
        assertEquals(emptySet<Int>(), ChatMark.marksOf(null))
    }

    @Test
    fun `the button is only on the owner's own messages when markable`() {
        assertTrue(ChatMark.offered(true, "user", 3, emptySet()))
        assertFalse(ChatMark.offered(false, "user", 3, emptySet()))
        assertFalse(ChatMark.offered(true, "assistant", 3, emptySet()))
        assertFalse(ChatMark.offered(true, "support", 3, emptySet()))
        assertFalse(ChatMark.offered(true, "chatbot", 3, emptySet()))
        assertFalse(ChatMark.offered(true, "user", null, emptySet()))
        assertFalse(ChatMark.offered(true, "user", -1, emptySet()))
        // A turn that already has a divider uses the divider's Remove instead.
        assertFalse(ChatMark.offered(true, "user", 3, setOf(3)))
        assertTrue(ChatMark.dividerAbove(3, setOf(3)))
        assertFalse(ChatMark.dividerAbove(4, setOf(3)))
        assertFalse(ChatMark.dividerAbove(null, setOf(3)))
        assertTrue(ChatMark.full((0 until 20).toSet()))
        assertFalse(ChatMark.full((0 until 19).toSet()))
    }

    @Test
    fun `the conversation read carries marks, markable and mark_why`() {
        val t = ChatLog.transcript(
            obj(
                """{"ok":true,"id":"$chat","title":"T","marks":[2,5],"markable":true,"mark_why":"",
                    "turns":[{"role":"user","text":"a","idx":0}]}""",
            ),
        )!!
        assertEquals(setOf(2, 5), t.marks)
        assertTrue(t.markable)
        assertNull(t.markWhy)
        val no = ChatLog.transcript(
            obj("""{"id":"$chat","markable":false,"mark_why":"${w("mark_why_short")}","turns":[]}"""),
        )!!
        assertFalse(no.markable)
        assertEquals(w("mark_why_short"), no.markWhy)
        // An older PC says nothing: no buttons, no dividers.
        val old = ChatLog.transcript(obj("""{"id":"$chat","turns":[]}"""))!!
        assertFalse(old.markable)
        assertEquals(emptySet<Int>(), old.marks)
        // A mark_why is only ever an error's sentence.
        assertEquals(w("mark_why_short"), ChatMark.errorSentence("not_markable", null, no.markWhy))
    }
}
