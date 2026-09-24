package com.jarvis.client

import com.jarvis.client.net.Heard
import com.jarvis.client.net.JarvisJson
import com.jarvis.client.voice.PrivateAloud
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.jsonObject
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

/**
 * "Private answers stay on screen" when the phone speaks
 * (docs/JARVIS-API.md section 16, "What the apps must do about private
 * answers"). The utterance replies are the PC's REAL ones -
 * jarvis_speech.hear().as_dict() - and the headers start from the real
 * router's decision (jarvis_router.choose().as_dict()), both from
 * `contract/phone-voice-cases.json` (tools/gen_phone_voice_cases.py).
 * `injected_facts` is added to a real header where a test needs it: the
 * PC's chat route adds it, and that route is not in this repository.
 */
class PrivateAloudTest {

    private val answers: JsonObject = run {
        val text = requireNotNull(javaClass.classLoader?.getResource("contract/phone-voice-cases.json")) {
            "contract/phone-voice-cases.json is missing - run tools/gen_phone_voice_cases.py"
        }.readText()
        (JarvisJson.parseToJsonElement(text) as JsonObject)["strict"]!!.jsonObject["answers"]!!.jsonObject
    }

    private fun heard(case: String): Heard =
        JarvisJson.decodeFromJsonElement(Heard.serializer(), answers["heard"]!!.jsonObject[case]!!)

    /**
     * A real router header with `injected_facts` and `injected_sensitive`
     * set as asked. [sensitive] null takes `injected_sensitive` OUT, which is
     * what a PC from before the owner's decision of 2026-09-24 sends.
     */
    private fun header(case: String, injected: Int? = null, sensitive: Int? = null): String {
        val o = answers["route"]!!.jsonObject[case]!!.jsonObject - "injected_sensitive"
        val withFacts = if (injected == null) o else o + ("injected_facts" to JsonPrimitive(injected))
        val withSensitive = if (sensitive == null) withFacts else withFacts + ("injected_sensitive" to JsonPrimitive(sensitive))
        return JsonObject(withSensitive).toString()
    }

    /**
     * A real utterance reply with `sensitive_aloud` set. The phone voice
     * fixture (tools/gen_phone_voice_cases.py) does not carry the field yet
     * - its regeneration is the backend's - so it is written in here.
     */
    private fun heardWith(case: String, sensitiveAloud: Boolean): Heard {
        val o = answers["heard"]!!.jsonObject[case]!!.jsonObject
        return JarvisJson.decodeFromJsonElement(
            Heard.serializer(), JsonObject(o + ("sensitive_aloud" to JsonPrimitive(sensitiveAloud))),
        )
    }

    private val live = PrivateAloud.Watch(runs = 4, drops = 1, live = true)

    private fun may(h: Heard, route: String?, now: PrivateAloud.Watch = live) =
        PrivateAloud.mayRead(h, PrivateAloud.route(route), live, now)

    @Test
    fun `the real reply carries both fields`() {
        assertTrue(heard("private_question").questionPrivate)
        assertFalse(heard("private_question").privateAloud)
        assertFalse(heard("plain_question").questionPrivate)
        assertTrue(heard("voice_is_enough").privateAloud)
    }

    @Test
    fun `a plain question with nothing private about it is read aloud`() {
        assertTrue(may(heard("plain_question"), header("plain")))
        assertTrue(may(heard("plain_question"), header("plain", injected = 0)))
        // No header at all (an older PC): nothing says it is private.
        assertTrue(may(heard("plain_question"), null))
    }

    @Test
    fun `a question the PC marked private is not`() {
        assertFalse(may(heard("private_question"), header("no_cloud_lane")))
    }

    @Test
    fun `the router's private gate is not`() {
        assertEquals(PrivateAloud.Route(privateGate = true, injectedFacts = 0), PrivateAloud.route(header("private")))
        assertFalse(may(heard("plain_question"), header("private")))
    }

    @Test
    fun `remembered facts are read aloud by default - the owner's choice`() {
        assertTrue(heard("plain_question").memoryAloud)
        assertTrue(may(heard("plain_question"), header("plain", injected = 3, sensitive = 0)))
        // Asking about memory is not a private question while memory is aloud.
        assertFalse(heard("memory_question").questionPrivate)
        assertTrue(may(heard("memory_question"), header("plain", injected = 2, sensitive = 0)))
    }

    @Test
    fun `with memory kept on screen, remembered facts in the answer are not`() {
        val h = heard("memory_on_screen")
        assertFalse(h.memoryAloud)
        assertFalse(may(h, header("plain", injected = 3)))
        assertTrue(may(h, header("plain")))
        assertTrue(heard("memory_question_on_screen").questionPrivate)
        assertFalse(may(heard("memory_question_on_screen"), header("plain")))
    }

    @Test
    fun `memory aloud never opens email, notes or a tool`() {
        assertFalse(may(heard("private_question"), header("no_cloud_lane")))
        assertFalse(may(heard("plain_question"), header("private", injected = 1)))
        assertFalse(may(heard("plain_question"), header("plain", injected = 1), live.copy(runs = 5)))
    }

    @Test
    fun `a tool that ran while it was written stops the reading`() {
        assertFalse(may(heard("plain_question"), header("plain"), live.copy(runs = 5)))
    }

    @Test
    fun `not knowing whether a tool ran counts as a tool having run`() {
        // The stream dropped and came back while the answer was written.
        assertFalse(may(heard("plain_question"), header("plain"), live.copy(drops = 2)))
        // The stream is not live now.
        assertFalse(may(heard("plain_question"), header("plain"), live.copy(live = false)))
        // Nor was it when the question was asked.
        assertFalse(
            PrivateAloud.mayRead(heard("plain_question"), PrivateAloud.route(header("plain")), live.copy(live = false), live),
        )
    }

    @Test
    fun `voice check is enough reads it all`() {
        val h = heard("voice_is_enough")
        assertTrue(may(h, header("private", injected = 5, sensitive = 0), live.copy(runs = 9)))
    }

    @Test
    fun `an older PC's reply - no fields - counts as not allowed aloud`() {
        val o = answers["heard"]!!.jsonObject["plain_question"]!!.jsonObject
        val older = JarvisJson.decodeFromJsonElement(
            Heard.serializer(), JsonObject(o - setOf("private_aloud", "question_private", "memory_aloud")),
        )
        assertFalse(older.privateAloud)
        assertFalse(older.memoryAloud)
        // ...and is then held to the same rule: read only when nothing says private.
        assertFalse(may(older, header("plain", injected = 1)))
        assertTrue(may(older, header("plain")))
    }

    // ------------------------- sensitive saved facts (owner, 2026-09-24) --

    @Test
    fun `the header's sensitive count is read, and fails closed when it is missing`() {
        assertEquals(2, PrivateAloud.route(header("plain", injected = 3, sensitive = 2)).injectedSensitive)
        assertEquals(0, PrivateAloud.route(header("plain", injected = 3, sensitive = 0)).injectedSensitive)
        // Missing, with facts in the answer: every one may be sensitive.
        assertEquals(3, PrivateAloud.route(header("plain", injected = 3)).injectedSensitive)
        // Missing, with no facts: nothing sensitive.
        assertEquals(0, PrivateAloud.route(header("plain", injected = 0)).injectedSensitive)
        assertEquals(0, PrivateAloud.route(header("plain")).injectedSensitive)
        // Not a real count (a string, negative): treated as missing - closed.
        val o = answers["route"]!!.jsonObject["plain"]!!.jsonObject + ("injected_facts" to JsonPrimitive(2))
        assertEquals(2, PrivateAloud.route(JsonObject(o + ("injected_sensitive" to JsonPrimitive("0"))).toString()).injectedSensitive)
        assertEquals(2, PrivateAloud.route(JsonObject(o + ("injected_sensitive" to JsonPrimitive(-1))).toString()).injectedSensitive)
        assertEquals(PrivateAloud.SILENT_ROUTE, PrivateAloud.route(null))
    }

    @Test
    fun `an answer that used a sensitive saved fact stays on screen, even with memories read aloud`() {
        val h = heard("plain_question")
        assertTrue(h.memoryAloud)
        // The fixture predates the field: missing reads as false.
        assertFalse(h.sensitiveAloud)
        assertFalse(may(h, header("plain", injected = 3, sensitive = 1)))
        assertTrue(may(h, header("plain", injected = 3, sensitive = 0)))
        // A PC that does not say which facts were sensitive: on screen.
        assertFalse(may(h, header("plain", injected = 3)))
    }

    @Test
    fun `even voice check is enough keeps a sensitive fact on screen`() {
        val h = heard("voice_is_enough")
        assertTrue(h.privateAloud)
        assertFalse(may(h, header("plain", injected = 2, sensitive = 1)))
        assertFalse(may(h, header("plain", injected = 2)))
        // ...until the owner chose to hear them, and this voice passed a real check.
        assertTrue(may(heardWith("voice_is_enough", sensitiveAloud = true), header("plain", injected = 2, sensitive = 1)))
    }

    @Test
    fun `sensitive aloud opens only the sensitive step, nothing else`() {
        val h = heardWith("plain_question", sensitiveAloud = true)
        assertTrue(h.sensitiveAloud)
        assertTrue(may(h, header("plain", injected = 2, sensitive = 2)))
        // Missing count, facts in it: also allowed - the owner said sensitive ones may be read.
        assertTrue(may(h, header("plain", injected = 2)))
        // Email, notes, the router's private gate and tools still stay on screen.
        assertFalse(may(heardWith("private_question", sensitiveAloud = true), header("no_cloud_lane")))
        assertFalse(may(h, header("private", injected = 2, sensitive = 2)))
        assertFalse(may(h, header("plain", injected = 2, sensitive = 2), live.copy(runs = 5)))
        // With memories kept on screen, facts in the answer still keep it there.
        assertFalse(may(heardWith("memory_on_screen", sensitiveAloud = true), header("plain", injected = 2, sensitive = 2)))
    }

    @Test
    fun `before the header arrives nothing is read`() {
        assertFalse(PrivateAloud.mayRead(heard("plain_question"), null, live, live))
    }

    @Test
    fun `which step events mean a tool ran`() {
        fun step(phase: String) = JsonObject(mapOf("phase" to JsonPrimitive(phase), "tool" to JsonPrimitive("email")))
        assertTrue(PrivateAloud.isToolRun(step("tool_started")))
        assertTrue(PrivateAloud.isToolRun(step("tool_finished")))
        assertFalse(PrivateAloud.isToolRun(step("tool_refused")))
        assertFalse(PrivateAloud.isToolRun(step("model")))
        assertFalse(PrivateAloud.isToolRun(null))
    }

    @Test
    fun `an unreadable header says nothing either way`() {
        assertEquals(PrivateAloud.SILENT_ROUTE, PrivateAloud.route("not json"))
        assertEquals(PrivateAloud.SILENT_ROUTE, PrivateAloud.route(""))
        assertEquals("It's on your screen.", PrivateAloud.ON_SCREEN)
    }
}
