package com.jarvis.client

import com.jarvis.client.net.Handoff
import com.jarvis.client.net.JarvisJson
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.int
import kotlinx.serialization.json.jsonArray
import kotlinx.serialization.json.jsonObject
import kotlinx.serialization.json.jsonPrimitive
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNotNull
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test

/**
 * "Solve it here", read from what the PC REALLY answers.
 *
 * `contract/handoff-cases.json` is written by tools/gen_handoff_cases.py from
 * the real routes (jarvis_chatbot_routes.py over jarvis_handoff.py) with a
 * stand-in browser window - byte for byte the file the desktop builds
 * against. Its `words` are the PC's own sentences, which this phone must say
 * word for word.
 */
class HandoffTest {

    private val doc: JsonObject = run {
        val text = requireNotNull(javaClass.classLoader?.getResource("contract/handoff-cases.json")) {
            "contract/handoff-cases.json is missing - run tools/gen_handoff_cases.py"
        }.readText()
        JarvisJson.parseToJsonElement(text) as JsonObject
    }

    private fun obj(case: String): JsonObject = doc[case]!!.jsonObject

    private fun answer(case: String): Handoff.Answer {
        val o = obj(case)
        return Handoff.answer(o["code"]!!.jsonPrimitive.int, o["body"] as? JsonObject)
    }

    @Test
    fun `the words are the PC's own, every one`() {
        val w = obj("words")
        assertEquals(w.keys, Handoff.WORDS.keys)
        for ((key, words) in Handoff.WORDS) assertEquals(key, w[key]!!.jsonPrimitive.content, words)
        val e = obj("ended_words")
        assertEquals(e.keys, Handoff.ENDED.keys)
        for ((key, words) in Handoff.ENDED) assertEquals(key, e[key]!!.jsonPrimitive.content, words)
        assertEquals(doc["keys"]!!.jsonArray.map { it.jsonPrimitive.content }, Handoff.KEYS)
        assertEquals(doc["owner_codes"]!!.jsonArray.map { it.jsonPrimitive.content }.toSet(), Handoff.OWNER_CODES)
        assertEquals(obj("limits")["text_most"]!!.jsonPrimitive.int, Handoff.TEXT_MOST)
        val r = obj("routes")
        assertEquals(r["start"]!!.jsonPrimitive.content, Handoff.START_PATH)
        assertEquals(r["frame"]!!.jsonPrimitive.content, Handoff.FRAME_PATH)
        assertEquals(r["input"]!!.jsonPrimitive.content, Handoff.INPUT_PATH)
        assertEquals(r["end"]!!.jsonPrimitive.content, Handoff.END_PATH)
    }

    @Test
    fun `nothing waiting, another pause, or after Resume - no alert`() {
        assertNull(Handoff.offer(obj("offer_none")))
        assertNull(Handoff.offer(obj("offer_other_pause")))
        assertNull(Handoff.offer(obj("offer_after_resume")))
        assertNull("an older PC sends none", Handoff.offer(null))
    }

    @Test
    fun `a chatbot at a captcha - the site and the reason only, generic under App lock`() {
        val o = requireNotNull(Handoff.offer(obj("offer_captcha")))
        assertEquals("chatbot", o.kind)
        assertEquals("chat_000000000001", o.id)
        assertEquals("captcha", o.reason)
        assertEquals("Gemini", o.site)
        val (title, text) = Handoff.alert(o, locked = false)
        assertEquals("Gemini needs you", title)
        assertTrue(text, text.contains("captcha"))
        val (lt, lx) = Handoff.alert(o, locked = true)
        assertEquals(Handoff.ALERT_LOCKED, lt)
        assertTrue("the locked alert names the site", !lt.contains("Gemini") && !lx.contains("Gemini"))
        assertTrue("the locked alert names the reason", !lx.contains("captcha"))
        assertEquals("ho_0000000000000001", Handoff.offer(obj("offer_active"))!!.active)
        val sup = requireNotNull(Handoff.offer(obj("offer_support")))
        assertEquals("support", sup.kind)
        assertEquals("Groupon needs you", Handoff.alert(sup, false).first)
    }

    @Test
    fun `what is sent - the PC's shapes, nothing else`() {
        val o = requireNotNull(Handoff.offer(obj("offer_captcha")))
        assertEquals("{\"kind\":\"chatbot\",\"id\":\"chat_000000000001\"}", Handoff.startBody(o))
        assertNull(Handoff.startBody(o.copy(id = "chat_x")))
        val h = "ho_0000000000000001"
        assertEquals("{\"h\":\"$h\",\"type\":\"tap\",\"x\":0.5000,\"y\":0.2500}", Handoff.tapBody(h, 0.5f, 0.25f))
        assertNull(Handoff.tapBody(h, 1.2f, 0.5f))
        assertNull(Handoff.tapBody("ho_nope", 0.5f, 0.5f))
        assertEquals("{\"h\":\"$h\",\"type\":\"text\",\"text\":\"a \\\"b\\\"\"}", Handoff.textBody(h, "a \"b\""))
        assertNull("control characters go as keys", Handoff.textBody(h, "a\nb"))
        assertNull(Handoff.textBody(h, "x".repeat(Handoff.TEXT_MOST + 1)))
        assertNull(Handoff.textBody(h, ""))
        assertNotNull(Handoff.keyBody(h, "Enter"))
        assertNull(Handoff.keyBody(h, "F5"))
        assertNull(Handoff.keyBody(h, "Control+L"))
        assertTrue(Handoff.scrollBody(h, 99999)!!.contains("\"dy\":1500"))
        assertEquals("{\"h\":\"$h\"}", Handoff.endBody(h))
        assertEquals(Handoff.HELD_STALE, Handoff.inputHeld(stale = true))
        assertNull(Handoff.inputHeld(stale = false))
        assertTrue(Handoff.SHOWN_KEYS.all { it in Handoff.KEYS })
    }

    @Test
    fun `what comes back - a picture, too soon, ended, refused`() {
        val start = obj("start")["body"]!!.jsonObject
        assertTrue(Handoff.validHid(start["handoff"]!!.jsonPrimitive.content))
        val pic = answer("frame") as Handoff.Answer.Picture
        assertEquals(390, pic.width)
        assertEquals(300, pic.height)
        assertEquals(1, pic.seq)
        assertTrue(pic.jpeg.startsWith("/9j/"))
        assertTrue(answer("frame_too_soon") is Handoff.Answer.TooSoon)
        val left = answer("frame_left") as Handoff.Answer.Ended
        assertEquals("left", left.why)
        assertEquals(Handoff.ENDED["left"], left.words)
        assertEquals("resumed", (answer("input_after_resume") as Handoff.Answer.Ended).why)
        assertTrue(answer("frame_after_end") is Handoff.Answer.Ended)
        assertEquals(200, obj("tap")["code"]!!.jsonPrimitive.int)
        assertEquals(200, obj("text")["code"]!!.jsonPrimitive.int)
        assertTrue(answer("key_refused") is Handoff.Answer.Failed)
        assertEquals(200, obj("end")["code"]!!.jsonPrimitive.int)
    }

    @Test
    fun `a tap lands where it was on the picture, and the margin is not the page`() {
        // A 400x300 picture in a 400x600 box: drawn 400x300, 150 from the top.
        val (fx, fy) = requireNotNull(Handoff.fractions(200f, 300f, 400f, 600f, 400, 300))
        assertEquals(0.5f, fx, 0.001f)
        assertEquals(0.5f, fy, 0.001f)
        assertNull("above the picture", Handoff.fractions(200f, 100f, 400f, 600f, 400, 300))
        assertNull("no picture yet", Handoff.fractions(1f, 1f, 400f, 600f, 0, 0))
        val (cx, cy) = requireNotNull(Handoff.fractions(0f, 150f, 400f, 600f, 400, 300))
        assertEquals(0f, cx, 0.001f)
        assertEquals(0f, cy, 0.001f)
    }
}
