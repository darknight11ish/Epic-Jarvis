package com.jarvis.client.net

import kotlinx.serialization.json.Json
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertNotNull
import kotlin.test.assertNull
import kotlin.test.assertTrue

/**
 * The pure half of "Write like me": the phone's parser and its wording.
 * Runs on a plain JVM (`./gradlew :app:testDebugUnitTest --tests '*VoiceprintTest*'`).
 */
class VoiceprintTest {
    private fun parse(json: String) = Voiceprint.parse(Json.parseToJsonElement(json) as kotlinx.serialization.json.JsonObject)

    @Test
    fun a_page_is_rendered_from_the_pc_answer() {
        val view = parse(
            """{"available":true,"enabled":true,"count":2,"scrubber":true,
                "samples":[{"id":"vp1","text":"Hello [name]","kind":"sample"},
                           {"id":"vp2","text":"Second","kind":"edit"}]}"""
        )
        assertNotNull(view)
        assertTrue(view.enabled)
        assertEquals(2, view.samples.size)
        assertEquals("vp1", view.samples[0].id)
        assertEquals("Hello [name]", view.samples[0].text)
    }

    @Test
    fun an_older_pc_is_null_not_an_empty_page() {
        assertNull(parse("""{"available":false}"""))
    }

    @Test
    fun a_malformed_row_is_dropped() {
        val view = parse("""{"available":true,"samples":[{"nope":1},{"id":"vp1","text":"x"}]}""")
        assertNotNull(view)
        assertEquals(1, view.samples.size)
    }

    @Test
    fun the_switch_defaults_off() {
        val view = parse("""{"available":true,"samples":[]}""")
        assertNotNull(view)
        assertEquals(false, view.enabled)
        assertEquals(Voiceprint.EMPTY, view.message)
    }

    @Test
    fun sample_guard_refuses_empty_and_over_long() {
        assertNotNull(Voiceprint.sampleProblem("  "))
        assertNotNull(Voiceprint.sampleProblem("x".repeat(Voiceprint.MAX_TEXT + 1)))
        assertNull(Voiceprint.sampleProblem("A normal message."))
    }

    @Test
    fun forget_asks_first_and_quotes_the_sample() {
        val ask = Voiceprint.forgetAsk(Voiceprint.Sample("vp1", "Please send the invoice", "sample"))
        assertTrue(ask.startsWith("Forget this sample?"))
        assertTrue(ask.contains("Please send the invoice"))
        assertTrue(ask.contains("cannot be undone"))
    }

    @Test
    fun one_switch_tap_is_one_boolean_body() {
        assertEquals(Voiceprint.enabledBody(true), Json.parseToJsonElement("""{"on":true}"""))
        assertEquals(Voiceprint.enabledBody(false), Json.parseToJsonElement("""{"on":false}"""))
    }
}
