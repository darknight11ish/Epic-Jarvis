package com.jarvis.client

import com.jarvis.client.call.CallRecordRules
import com.jarvis.client.net.CallRecordWire
import com.jarvis.client.net.JarvisJson
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.contentOrNull
import kotlinx.serialization.json.intOrNull
import kotlinx.serialization.json.jsonObject
import kotlinx.serialization.json.jsonPrimitive
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test
import java.time.ZoneId
import java.util.Base64

/**
 * The phone's half of the frozen call-recording contract (2026-11-04), key by
 * key.
 *
 * A typo in a JSON key is invisible until a real call: the PC would answer
 * 400, the phone would keep the audio and retry, and the recording would sit
 * on the phone for ever with nothing naming the reason. So every body is
 * parsed back here and checked against the contract as written, the base64 is
 * round-tripped, and the directive parser is held to "arm", "stop" and
 * silence for everything else.
 */
class CallRecordWireTest {

    private fun obj(json: String): JsonObject = JarvisJson.parseToJsonElement(json).jsonObject

    private fun JsonObject.s(key: String): String? = (this[key] as? JsonPrimitive)?.contentOrNull

    private fun JsonObject.i(key: String): Int? = (this[key] as? JsonPrimitive)?.intOrNull

    // ------------------------------------------------------------- start ---

    @Test
    fun `start carries the five contract fields and nothing that names the phone`() {
        val zone = ZoneId.of("America/Los_Angeles")
        val ms = java.time.ZonedDateTime.of(2026, 11, 4, 13, 41, 39, 0, zone).toInstant().toEpochMilli()
        val body = obj(CallRecordWire.startBody(ms, zone))
        assertEquals("2026-11-04T13:41:39-08:00", body.s("started_at"))
        assertEquals(16_000, body.i("sample_rate"))
        assertEquals(1, body.i("channels"))
        assertEquals("s16le", body.s("format"))
        assertEquals("phone", body.s("device"))
        assertEquals(
            "exactly the contract's five fields; no model, no token, no path",
            setOf("started_at", "sample_rate", "channels", "format", "device"),
            body.keys,
        )
    }

    // ------------------------------------------------------------- chunk ---

    @Test
    fun `chunk carries the session, the sequence and base64 pcm`() {
        val pcm = ByteArray(64) { (it * 3).toByte() }
        val body = obj(CallRecordWire.chunkBody("pc-1", 7, pcm))
        assertEquals("pc-1", body.s("session"))
        assertEquals(7, body.i("seq"))
        val decoded = Base64.getDecoder().decode(body.s("data_b64"))
        assertTrue("the bytes must survive base64 unchanged", pcm.contentEquals(decoded))
        assertEquals(setOf("session", "seq", "data_b64"), body.keys)
    }

    @Test
    fun `a full chunk is inside the contract's 32-64 KB window`() {
        val pcm = ByteArray(CallRecordRules.CHUNK_BYTES)
        val body = obj(CallRecordWire.chunkBody("pc-1", 1, pcm))
        val b64 = body.s("data_b64").orEmpty()
        assertEquals("base64 of 64 KiB is 87,384 characters", 87_384, b64.length)
        assertEquals(
            "the decoded size must be the PCM it was made from",
            CallRecordRules.CHUNK_BYTES,
            Base64.getDecoder().decode(b64).size,
        )
    }

    // ------------------------------------------------------------ finish ---

    @Test
    fun `finish carries the length, the title and the consent flag`() {
        val body = obj(CallRecordWire.finishBody("pc-1", 252L, "Call - 2026-11-04 13:41"))
        assertEquals("pc-1", body.s("session"))
        assertEquals(252L, (body["duration_sec"] as JsonPrimitive).content.toLong())
        assertEquals("Call - 2026-11-04 13:41", body.s("title"))
        assertEquals("on", body.s("consent_notice"))
        assertEquals(setOf("session", "duration_sec", "title", "consent_notice"), body.keys)
    }

    @Test
    fun `finish without a title sends no title at all`() {
        val body = obj(CallRecordWire.finishBody("pc-1", 1L, null))
        assertEquals(setOf("session", "duration_sec", "consent_notice"), body.keys)
        val blank = obj(CallRecordWire.finishBody("pc-1", 1L, "   "))
        assertEquals(setOf("session", "duration_sec", "consent_notice"), blank.keys)
    }

    @Test
    fun `a negative duration is clamped rather than sent`() {
        val body = obj(CallRecordWire.finishBody("pc-1", -5L))
        assertEquals("0", body.s("duration_sec"))
    }

    // ----------------------------------------------------------- answers ---

    @Test
    fun `start reads the session id and refuses an ok false`() {
        assertEquals("abc", CallRecordWire.started(obj("""{"ok":true,"session":"abc"}""")))
        assertNull(CallRecordWire.started(obj("""{"ok":false,"session":"abc"}""")))
        assertNull(CallRecordWire.started(obj("""{"ok":true}""")))
        assertNull(CallRecordWire.started(obj("""{"ok":true,"session":"  "}""")))
        assertNull(CallRecordWire.started(null))
    }

    @Test
    fun `chunk reads the byte count and an ok false is a refusal`() {
        assertEquals(65_536L, CallRecordWire.ackedBytes(obj("""{"ok":true,"bytes":65536}""")))
        assertNull(CallRecordWire.ackedBytes(obj("""{"ok":false,"bytes":1}""")))
        assertNull(CallRecordWire.ackedBytes(null))
    }

    @Test
    fun `finish reads the note and a pending note says it is pending`() {
        val done = CallRecordWire.finished(obj("""{"ok":true,"note":"pending","receipt":"r-1"}"""))
        assertEquals("pending", done?.note)
        assertEquals("r-1", done?.receipt)
        assertEquals(CallRecordRules.SENT_TEXT, done?.said())
        val wrote = CallRecordWire.finished(obj("""{"ok":true,"note":"Calls/2026-11-04 13.41.md"}"""))
        assertTrue(wrote?.said().orEmpty().contains("Calls/2026-11-04 13.41.md"))
        assertNull(CallRecordWire.finished(obj("""{"ok":false}""")))
    }

    @Test
    fun `a body that never says ok is accepted, because the contract only adds it to say no`() {
        assertTrue(CallRecordWire.ok(obj("""{"bytes":1}""")))
        assertFalse(CallRecordWire.ok(obj("""{"ok":false}""")))
    }

    // --------------------------------------------------------- directive ---

    @Test
    fun `the arm directive is read from the route header`() {
        val header = """{"where":"local","call_record":{"action":"arm"}}"""
        assertEquals(CallRecordRules.Event.ARM, CallRecordWire.directive(header))
        assertEquals("arm", CallRecordWire.actionIn(header))
    }

    @Test
    fun `the stop directive is read the same way`() {
        val header = """{"call_record":{"action":"stop"}}"""
        assertEquals(CallRecordRules.Event.OWNER_STOP, CallRecordWire.directive(header))
    }

    @Test
    fun `a header without the directive, or with an unknown action, does nothing`() {
        assertNull(CallRecordWire.directive(null))
        assertNull(CallRecordWire.directive(""))
        assertNull(CallRecordWire.directive("""{"where":"local"}"""))
        // Never a guess: an action this app does not know must not arm a
        // microphone, and must not stop a recording either.
        assertNull(CallRecordWire.directive("""{"call_record":{"action":"pause"}}"""))
        assertNull(CallRecordWire.directive("""{"call_record":{"action":42}}"""))
        // An answer whose header is not JSON is silence, never a crash.
        assertNull(CallRecordWire.directive("not json at all"))
        assertNull(CallRecordWire.directive("""["call_record"]"""))
        assertNull(CallRecordWire.directive("""{"call_record":"arm"}"""))
    }

    @Test
    fun `the directive can ride beside the other machine fields`() {
        val header = """{"open_brain":"history","file_under":3,"call_record":{"action":"arm"}}"""
        assertEquals(CallRecordRules.Event.ARM, CallRecordWire.directive(header))
    }

    // -------------------------------------------------------------- paths ---

    @Test
    fun `the three routes are exactly the contract's`() {
        assertEquals(
            listOf(
                "/api/call/recording/start",
                "/api/call/recording/chunk",
                "/api/call/recording/finish",
            ),
            CallRecordWire.PATHS,
        )
    }
}
