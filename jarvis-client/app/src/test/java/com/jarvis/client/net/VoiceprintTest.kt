package com.jarvis.client.net

import kotlinx.serialization.json.Json
import kotlinx.serialization.json.JsonObject
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNotNull
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test

/**
 * The pure half of "Write like me": the phone's parser and its wording.
 * Runs on a plain JVM (`./gradlew :app:testDebugUnitTest --tests '*VoiceprintTest*'`).
 *
 * JUnit4 is the app's test dependency (`junit:junit:4.13.2` in app/build.gradle.kts),
 * and the other JVM tests in this folder import `org.junit.Test` / `org.junit.Assert.*`
 * the same way. `parse()` returns a nullable View on purpose (an older PC has no
 * page), so each test that needs the value binds it with `requireNotNull` once.
 */
class VoiceprintTest {
    private fun parse(json: String): Voiceprint.View? =
        Voiceprint.parse(Json.parseToJsonElement(json) as JsonObject)

    // Every fixture is the shape `jarvis_voiceprint.handle_get()` really
    // answers (measured 2026-10-20): samples/count at the top level, the
    // switch and its flags inside "status". A flat fixture would let a switch
    // that always renders OFF pass.
    @Test
    fun a_page_is_rendered_from_the_pc_answer() {
        val view = requireNotNull(parse(
            """{"ok":true,"count":2,
                "status":{"available":true,"enabled":true,"scrubber":true,"samples":2},
                "samples":[{"id":"vp1","text":"Hello [name]","kind":"sample"},
                           {"id":"vp2","text":"Second","kind":"edit"}]}"""
        ))
        assertTrue("the switch reads the PC's own status block", view.enabled)
        assertEquals(2, view.samples.size)
        assertEquals("vp1", view.samples[0].id)
        assertEquals("Hello [name]", view.samples[0].text)
    }

    @Test
    fun an_older_pc_is_null_not_an_empty_page() {
        assertNull(parse("""{"status":{"available":false}}"""))
    }

    @Test
    fun a_malformed_row_is_dropped() {
        val view = requireNotNull(parse(
            """{"status":{"available":true},
                "samples":[{"nope":1},{"id":"vp1","text":"x"}]}"""
        ))
        assertEquals(1, view.samples.size)
    }

    @Test
    fun the_switch_defaults_off() {
        val view = requireNotNull(parse("""{"status":{"available":true},"samples":[]}"""))
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
        assertEquals(Voiceprint.enabledBody(true), Json.parseToJsonElement("""{"enabled":true}"""))
        assertEquals(Voiceprint.enabledBody(false), Json.parseToJsonElement("""{"enabled":false}"""))
    }
}
