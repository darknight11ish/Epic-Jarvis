package com.jarvis.client

import com.jarvis.client.net.JarvisJson
import com.jarvis.client.voice.LiveRules
import kotlinx.serialization.json.JsonArray
import kotlinx.serialization.json.JsonNull
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.boolean
import kotlinx.serialization.json.booleanOrNull
import kotlinx.serialization.json.float
import kotlinx.serialization.json.int
import kotlinx.serialization.json.jsonArray
import kotlinx.serialization.json.jsonObject
import kotlinx.serialization.json.jsonPrimitive
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

/**
 * Jarvis Live's rules on the phone, held to the table both apps share
 * (`src/test/resources/contract/live-cases.json`, written by
 * tools/gen_live_cases.py from backend/jarvis_live.py; the desktop's
 * tests/jarvis-live.mjs runs the same file through live-rules.js).
 */
class LiveRulesTest {

    private val table: JsonObject = run {
        val text = requireNotNull(javaClass.classLoader?.getResource("contract/live-cases.json")) {
            "contract/live-cases.json is missing - run python3 tools/gen_live_cases.py"
        }.readText()
        JarvisJson.parseToJsonElement(text) as JsonObject
    }

    private val statuses: JsonObject = table["statuses"]!!.jsonObject

    private fun status(name: String): JsonObject? = statuses[name] as? JsonObject

    private fun cases(key: String): List<JsonObject> = table[key]!!.jsonArray.map { it.jsonObject }

    private fun JsonObject.s(key: String): String = this[key]!!.jsonPrimitive.content

    private fun JsonObject.b(key: String): Boolean =
        (this[key] as? JsonPrimitive)?.booleanOrNull ?: false

    private fun strings(o: JsonObject): Map<String, String> = o.mapValues { it.value.jsonPrimitive.content }

    @Test
    fun `the fixed words are the PC's`() {
        assertEquals(table.s("title"), LiveRules.TITLE)
        assertEquals(table.s("dot"), LiveRules.DOT)
        assertEquals(table.s("link_words"), LiveRules.LINK_WORDS)
        assertEquals(table.s("link_lost_said"), LiveRules.LINK_LOST_SAID)
        assertEquals(table.s("side_talk_mark"), LiveRules.SIDE_TALK_MARK)
        assertEquals(strings(table["lines"]!!.jsonObject), LiveRules.LINES)
        assertEquals(strings(table["seen"]!!.jsonObject), LiveRules.SEEN)
        assertEquals(table["voice_pauses"]!!.jsonArray.map { it.jsonPrimitive.content }, LiveRules.VOICE_PAUSES)
        assertEquals(table["card_pauses"]!!.jsonArray.map { it.jsonPrimitive.content }, LiveRules.CARD_PAUSES)
        assertEquals(table.s("interrupt_title"), LiveRules.INTERRUPT_TITLE)
        val interrupt = cases("interrupt").map {
            LiveRules.Choice(it.s("id"), it.s("label"), it.b("recommended"), it.s("detail"))
        }
        assertEquals(interrupt, LiveRules.INTERRUPT)
        assertEquals(table.s("stop_talking"), LiveRules.STOP_TALKING)
        val turn = table["turn"]!!.jsonObject
        assertEquals(turn["ask_after_ms"]!!.jsonPrimitive.int.toLong(), LiveRules.TURN_ASK_AFTER_MS)
        assertEquals(turn["max_pause_ms"]!!.jsonPrimitive.int.toLong(), LiveRules.TURN_MAX_PAUSE_MS)
        assertEquals(table["duck_volume"]!!.jsonPrimitive.float, LiveRules.DUCK_VOLUME, 0.0001f)
        assertEquals(table["max_chips"]!!.jsonPrimitive.int, LiveRules.MAX_CHIPS)
    }

    @Test
    fun `the sign, every case`() {
        val all = cases("sign")
        assertTrue("only ${all.size} cases", all.size > 40)
        for (c in all) {
            val w = c["want"]!!.jsonObject
            val want = LiveRules.Sign(
                show = w.b("show"), title = w.s("title"), detail = w.s("detail"), stop = w.s("stop"),
                mute = w.s("mute"), carryOn = w.b("carry_on"), resume = w.b("resume"),
            )
            val got = LiveRules.sign(status(c.s("status")), c.s("me"), c.b("stale"), c.b("thinking"), c.b("short"))
            assertEquals(c.s("name"), want, got)
        }
    }

    @Test
    fun `may it listen, and may the microphone be open, every case`() {
        val all = cases("listen")
        assertTrue("only ${all.size} cases", all.size > 100)
        for (c in all) {
            val w = c["want"]!!.jsonObject
            val want = LiveRules.Listen(w.b("listen"), w.b("mic"), w.s("why"))
            val got = LiveRules.listen(
                status(c.s("status")), c.s("me"), stale = c.b("stale"), cardShown = c.b("card_shown"),
                answering = c.b("answering"), appLocked = c.b("app_locked"), interrupt = c.s("interrupt"),
            )
            assertEquals(c.s("name"), want, got)
        }
    }

    @Test
    fun `what to do with the PC's answer, every case`() {
        for (c in cases("reply")) {
            val w = c["want"]!!.jsonObject
            val want = LiveRules.Reply(LiveRules.Action.valueOf(w.s("action").uppercase()), w.s("say"))
            assertEquals(c.s("name"), want, LiveRules.reply(LiveRules.ReplyIn.of(c["heard"]!!.jsonObject)))
        }
    }

    @Test
    fun `the fixed line when the session changes by itself, every case`() {
        for (c in cases("transition")) {
            assertEquals(c.s("name"), c.s("want"), LiveRules.transition(status(c.s("before")), status(c.s("after")), c.s("me")))
        }
    }

    @Test
    fun `tap buttons after a spoken question, every case`() {
        for (c in cases("chips")) {
            val want = c["want"]!!.jsonArray.map { it.jsonPrimitive.content }
            assertEquals(c.s("name"), want, LiveRules.chips(c.s("answer"), c.b("card_shown")))
        }
    }

    @Test
    fun `side talk is only the marker, and speech waits while it could be it`() {
        for (c in cases("side_talk")) assertEquals(c.s("name"), c.b("side_talk"), LiveRules.isSideTalk(c.s("answer")))
        for (c in cases("side_talk_partial")) {
            assertEquals(c.s("partial"), c.b("hold"), LiveRules.couldBeSideTalk(c.s("partial")))
        }
    }

    @Test
    fun `interrupting ducks first, and a second thought joins the question`() {
        for (c in cases("barge")) assertEquals(c.s("event"), c.s("want"), LiveRules.barge(c.s("event")))
        for (c in cases("fold")) {
            assertEquals(c.s("want"), LiveRules.fold(c.s("previous"), c.s("new"), c.b("sounded")))
        }
    }

    @Test
    fun `only fixed words go to the PC, and what the PC takes`() {
        val start = JarvisJson.parseToJsonElement(LiveRules.startBody()).jsonObject
        assertEquals("start", start.s("do"))
        assertEquals("phone", start.s("device"))
        assertEquals("button", start.s("by"))
        assertEquals(table["app_end_reasons"]!!.jsonArray.map { it.jsonPrimitive.content }.containsAll(LiveRules.END_REASONS), true)
        assertEquals("app_lock", JarvisJson.parseToJsonElement(LiveRules.stopBody("app_lock")).jsonObject.s("why"))
        assertEquals("owner", JarvisJson.parseToJsonElement(LiveRules.stopBody("locked")).jsonObject.s("why"))
        assertEquals("{\"do\":\"extend\",\"minutes\":20}", LiveRules.extendBody())
        assertEquals(null, LiveRules.extendBody(0))
        assertEquals(null, LiveRules.extendBody(500))
        val mute = JarvisJson.parseToJsonElement(LiveRules.muteBody(true, "call")).jsonObject
        assertEquals("mute", mute.s("do"))
        assertEquals("call", mute.s("why"))
        val muteWords = table["mute_words"]!!.jsonObject.keys
        assertTrue(muteWords.containsAll(LiveRules.MUTE_WHYS))
        assertEquals("owner", JarvisJson.parseToJsonElement(LiveRules.muteBody(false, "loud")).jsonObject.s("why"))
    }

    @Test
    fun `a phone call pauses Live, and never undoes the owner's own Mute`() {
        // AudioManager: NORMAL 0, RINGTONE 1, IN_CALL 2, IN_COMMUNICATION 3.
        assertFalse(LiveRules.onCall(0, ownVoiceCall = false))
        assertFalse(LiveRules.onCall(1, ownVoiceCall = false))
        assertTrue(LiveRules.onCall(2, ownVoiceCall = false))
        assertTrue(LiveRules.onCall(3, ownVoiceCall = false))
        assertFalse("Jarvis's own echo-cancelling mode is not a call", LiveRules.onCall(3, ownVoiceCall = true))
        val on = status("phone_on")
        val call = status("phone_call")
        val owner = status("phone_muted")
        assertEquals(true, LiveRules.callMuteChange(on, onCall = true))
        assertEquals(null, LiveRules.callMuteChange(on, onCall = false))
        assertEquals(false, LiveRules.callMuteChange(call, onCall = false))
        assertEquals(null, LiveRules.callMuteChange(call, onCall = true))
        assertEquals(null, LiveRules.callMuteChange(owner, onCall = false))
        assertEquals(null, LiveRules.callMuteChange(owner, onCall = true))
    }

    @Test
    fun `the camera switch, every case - off until the PC says ready`() {
        for (c in cases("camera")) {
            assertEquals(c.s("name"), c.b("want"), LiveRules.cameraShown(status(c.s("status")), c.s("me")))
        }
        assertFalse(LiveRules.cameraShown(status("desktop_camera_ready"), "desktop"))
        assertFalse(LiveRules.cameraShown(null))
        assertFalse(LiveRules.cameraShown(JsonObject(mapOf("on" to JsonNull))))
        assertTrue(table["camera"] is JsonArray)
    }
}
