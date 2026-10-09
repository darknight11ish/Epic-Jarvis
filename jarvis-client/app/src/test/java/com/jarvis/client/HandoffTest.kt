package com.jarvis.client

import com.jarvis.client.net.Handoff
import com.jarvis.client.net.HandoffMode
import com.jarvis.client.net.JarvisJson
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive
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

    // ---- how long it stays on offer (the owner's setting, 2026-10-08) ------

    @Test
    fun `the setting's two values, the default, and every word are the PC's`() {
        assertEquals(
            doc["modes"]!!.jsonArray.map { it.jsonPrimitive.content },
            HandoffMode.MODES,
        )
        assertEquals(doc["mode_default"]!!.jsonPrimitive.content, HandoffMode.DEFAULT)
        assertEquals("the default is the quick cut-off", "stop_early", HandoffMode.DEFAULT)
        assertEquals(doc["mode_patient"]!!.jsonPrimitive.content, HandoffMode.KEEP_OFFERING)
        val w = obj("mode_words")
        assertEquals(w.keys, HandoffMode.WORDS.keys)
        for ((key, words) in HandoffMode.WORDS) assertEquals(key, w[key]!!.jsonPrimitive.content, words)
        // The labels and the lines the screen draws come from the same table, not a second copy.
        for (id in HandoffMode.MODES) {
            assertEquals(HandoffMode.WORDS[id], HandoffMode.LABELS[id])
            assertEquals(HandoffMode.WORDS["${id}_detail"], HandoffMode.HELP[id])
        }
    }

    @Test
    fun `the setting's own route is not one of the hand-off's picture or input routes`() {
        val r = obj("routes")
        assertEquals(r["mode"]!!.jsonPrimitive.content, HandoffMode.PATH)
        assertEquals("/api/chatbot/handoff_mode", HandoffMode.PATH)
        assertTrue(
            "the setting is a sibling, never under /handoff/",
            !HandoffMode.PATH.startsWith("/api/chatbot/handoff" + "/"),
        )
        assertTrue("a tap or a picture is never sent to the setting",
            HandoffMode.PATH !in Handoff.WRITE_PATHS)
    }

    @Test
    fun `the setting's answers read as the PC's own lines`() {
        // The real GET, from `view()`: "Stop early" is chosen, a minute and the
        // 15-minute ceiling are the PC's own numbers, no card is waiting.
        val body = obj("mode_route_get")["body"]!!.jsonObject
        val v = HandoffMode.view(body)
        assertTrue(v.available)
        assertEquals("stop_early", v.mode)
        assertEquals(false, v.patient)
        assertEquals(false, v.waiting)
        assertEquals(60.0, v.idleSeconds, 0.001)
        assertEquals(900.0, v.ceilingSeconds, 0.001)
        assertEquals(HandoffMode.WORDS["stop_early_detail"], v.line)
        // A card waiting says so, and nothing has changed yet.
        val waiting = HandoffMode.view(
            JarvisJson.parseToJsonElement(
                "{\"mode\":\"stop_early\",\"waiting\":true,\"why\":\"\"}",
            ).jsonObject,
        )
        assertTrue(waiting.waiting)
        assertEquals(HandoffMode.WAITING_LINE, waiting.line)
        assertEquals("stop_early", waiting.mode)
        // A damaged file reads as the safe default, in the PC's own words.
        val damaged = HandoffMode.view(
            JarvisJson.parseToJsonElement(
                "{\"mode\":\"stop_early\",\"why\":${JsonPrimitive(HandoffMode.DAMAGED)}}",
            ).jsonObject,
        )
        assertEquals(HandoffMode.DAMAGED, damaged.line)
        // Anything not the PC's exact shape is "could not read it", never a guess.
        assertTrue(!HandoffMode.view(null).available)
        assertTrue(!HandoffMode.view(JarvisJson.parseToJsonElement("{\"mode\":\"forever\"}").jsonObject).available)
        assertEquals(HandoffMode.UNREAD, HandoffMode.view(null).line)
        assertEquals(HandoffMode.DEFAULT, HandoffMode.view(null).mode)
    }

    @Test
    fun `the body carries one of the two names and nothing else`() {
        assertEquals("{\"mode\":\"stop_early\"}", HandoffMode.body(HandoffMode.STOP_EARLY))
        assertEquals("{\"mode\":\"keep_offering\"}", HandoffMode.body(HandoffMode.KEEP_OFFERING))
        for (bad in listOf("", "on", "off", "patient", "stop", "STOP_EARLY")) {
            assertNull(bad, HandoffMode.body(bad))
        }
    }

    @Test
    fun `under the default the screen shows the PC's line naming the stuck window`() {
        // The PC's own two fixed sentences (`stuck_words`), and the same
        // substitution the desktop does.
        val s = obj("stuck_words")
        assertEquals(s.keys, Handoff.STUCK.keys)
        for ((key, words) in Handoff.STUCK) assertEquals(key, s[key]!!.jsonPrimitive.content, words)
        val (title, text) = Handoff.stuckLine("Gemini", "captcha")
        assertEquals("Gemini is waiting on this PC", title)
        assertTrue(text, text.contains("stuck on"))
        assertTrue(text, text.contains(Handoff.reasonWords("captcha")))
        assertTrue(text, text.contains("browser window on this PC"))
        // The real answer after a minute with nobody looking: the page is still
        // waiting AND the PC says which window it is stuck on.
        val offer = obj("mode_idle_offer")
        val stuck = requireNotNull(Handoff.stuck(offer))
        assertEquals(Handoff.stuckLine("Gemini", "captcha"), stuck)
        assertEquals("idle", (offer["ended"] as JsonObject)["ho_0000000000000004"]!!.jsonPrimitive.content)
        // Nothing stuck: no line (the offer in front of the owner, or an end
        // that was not "Stop early").
        assertNull(Handoff.stuck(obj("offer_captcha")))
        assertNull(Handoff.stuck(null))
        assertNull(Handoff.stuck(JarvisJson.parseToJsonElement("{\"stuck\":\"Gemini\"}").jsonObject))
        // `patient` rides on the status answer, and an older PC simply sends none.
        assertEquals(false, Handoff.patient(obj("mode_default_offer")))
        assertEquals(false, Handoff.patient(null))
    }
}
