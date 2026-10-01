package com.jarvis.client

import com.jarvis.client.net.JarvisJson
import com.jarvis.client.net.Quiz
import com.jarvis.client.net.QuizCloud
import kotlinx.serialization.json.JsonNull
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.buildJsonObject
import kotlinx.serialization.json.int
import kotlinx.serialization.json.jsonObject
import kotlinx.serialization.json.jsonPrimitive
import kotlinx.serialization.json.put
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNotNull
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test

/**
 * "Grade this better" on the phone (docs/STUDY-FROM-TEXT-DESIGN.md section 15,
 * JARVIS-API section 113; [QuizCloud]).
 */
class QuizCloudTest {

    private fun obj(json: String) = JarvisJson.parseToJsonElement(json) as JsonObject

    private val fixture: JsonObject = run {
        val text = requireNotNull(javaClass.classLoader?.getResource("contract/quiz-cloud-cases.json")) {
            "contract/quiz-cloud-cases.json is missing - run tools/gen_quiz_cloud_cases.py"
        }.readText()
        obj(text)
    }
    private val words get() = fixture["words"]!!.jsonObject
    private fun w(key: String) = words[key]!!.jsonPrimitive.content
    private val samples get() = fixture["samples"]!!.jsonObject

    private fun sample(name: String): Pair<Quiz.Reply, JsonObject> {
        val s = samples[name]!!.jsonObject
        return Quiz.Reply(s["status"]!!.jsonPrimitive.int, s["body"]!!.jsonObject) to s["expect"]!!.jsonObject
    }

    private fun str(o: JsonObject, k: String): String? =
        o[k]?.takeIf { it !is JsonNull }?.jsonPrimitive?.content
    private fun flag(o: JsonObject, k: String): Boolean? = o[k]?.jsonPrimitive?.content?.toBooleanStrictOrNull()

    @Test
    fun theWordsAreTheGeneratedFixturesWordsForWord() {
        listOf(
            "button" to QuizCloud.BUTTON,
            "title" to QuizCloud.TITLE,
            "intro" to QuizCloud.INTRO,
            "leaves" to QuizCloud.LEAVES,
            "cancel" to QuizCloud.CANCEL,
            "mark_label_prefix" to QuizCloud.MARK_LABEL_PREFIX,
        ).forEach { (key, mine) -> assertEquals(key, w(key), mine) }
    }

    @Test
    fun theSmallRulesAreTheFixturesRules() {
        assertEquals(fixture["poll_seconds"]!!.jsonPrimitive.int, QuizCloud.POLL_SECONDS)
        assertEquals(fixture["unknown_state_limit_seconds"]!!.jsonPrimitive.int, QuizCloud.UNKNOWN_STATE_LIMIT_SECONDS)
        assertEquals(fixture["payload_max"]!!.jsonPrimitive.int, QuizCloud.PAYLOAD_MAX)
        for ((state, phase) in fixture["phases"]!!.jsonObject) {
            assertEquals(state, phase.jsonPrimitive.content, QuizCloud.phase(state).name.lowercase())
            assertTrue(state, QuizCloud.isKnown(state))
        }
        for ((state, said) in fixture["state_words"]!!.jsonObject) {
            val r = QuizCloud.Request("0123456789ab", state, "", "q1", "Mistral", "api.mistral.ai", "model", 100, null, null, null)
            assertEquals(state, said.jsonPrimitive.content, QuizCloud.shown(r))
        }
    }

    @Test
    fun thePhasesMatchContract() {
        assertEquals(QuizCloud.Phase.WAITING, QuizCloud.phase("waiting"))
        assertEquals(QuizCloud.Phase.WORKING, QuizCloud.phase("sending"))
        assertEquals(QuizCloud.Phase.READY, QuizCloud.phase("ready"))
        assertEquals(QuizCloud.Phase.ENDED, QuizCloud.phase("denied"))
        assertEquals(QuizCloud.Phase.ENDED, QuizCloud.phase("timed_out"))
        assertEquals(QuizCloud.Phase.ENDED, QuizCloud.phase("withdrawn"))
        assertEquals(QuizCloud.Phase.ENDED, QuizCloud.phase("refused"))
        assertEquals(QuizCloud.Phase.ENDED, QuizCloud.phase("failed"))
        assertEquals(QuizCloud.Phase.WORKING, QuizCloud.phase("thinking_hard"))
        assertFalse(QuizCloud.isKnown("thinking_hard"))

        assertTrue(QuizCloud.keepPolling(QuizCloud.Phase.WAITING))
        assertTrue(QuizCloud.keepPolling(QuizCloud.Phase.WORKING))
        assertFalse(QuizCloud.keepPolling(QuizCloud.Phase.READY))
        assertFalse(QuizCloud.keepPolling(QuizCloud.Phase.ENDED))
    }

    @Test
    fun unknownStateGiveUpRule() {
        assertFalse(QuizCloud.giveUpOnUnknown(null, 100000L))
        assertFalse(QuizCloud.giveUpOnUnknown(1000L, 1000L + 179999L))
        assertTrue(QuizCloud.giveUpOnUnknown(1000L, 1000L + 180000L))
    }

    @Test
    fun allSamplesAreParsedCorrectly() {
        for ((name, _) in samples) {
            val (reply, expect) = sample(name)
            if (name.startsWith("info_")) {
                val info = QuizCloud.parseInfo(reply.body!!)
                assertNotNull(name, info)
                assertEquals(name, flag(expect, "available") ?: false, info!!.available)
                assertEquals(name, flag(expect, "ready") ?: false, info.ready)
                assertEquals(name, str(expect, "cheapest"), info.cheapest)
                assertEquals(name, expect["service_count"]!!.jsonPrimitive.int, info.services.size)
                continue
            }
            val outcome = QuizCloud.requestSaid(reply, "Not started.")
            assertEquals(name, flag(expect, "ok") ?: false, outcome.ok)
            if (outcome.ok) {
                assertNotNull(name, outcome.request)
                assertEquals(name, str(expect, "phase"), outcome.request!!.phase.name.lowercase())
                if (str(expect, "shown") != null) {
                    assertEquals(name, str(expect, "shown"), outcome.said)
                }
            } else {
                if (str(expect, "code") != null) {
                    assertEquals(name, str(expect, "code"), outcome.code)
                }
            }
        }
    }

    @Test
    fun everyContractRefusalKeepsPcsWords() {
        val refusals = fixture["refusals"]!!.jsonObject
        for ((code, r) in refusals) {
            val status = r.jsonObject["status"]!!.jsonPrimitive.int
            val msg = r.jsonObject["message"]!!.jsonPrimitive.content
            val body = buildJsonObject {
                put("ok", false)
                put("error", code)
                put("message", msg)
            }
            val outcome = QuizCloud.requestSaid(Quiz.Reply(status, body), "Not started.")
            assertFalse(code, outcome.ok)
            assertEquals(code, msg, outcome.said)
            assertEquals(code, code, outcome.code)
        }
    }
}
