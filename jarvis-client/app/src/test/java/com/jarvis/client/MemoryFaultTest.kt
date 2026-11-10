package com.jarvis.client

import com.jarvis.client.net.ApiError
import com.jarvis.client.net.JarvisJson
import com.jarvis.client.net.MemoryFault
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.jsonObject
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test

/**
 * The ONE learning-fault banner on the phone (docs/JARVIS-API.md section 213,
 * 2026-11-09; the memory-card research's measured finding). When a batch
 * learning check fails the PC records one fault, hides the cards it parked,
 * and both apps draw its own sentence with one "Retry now". These are the
 * contract's shapes and words; the composable that draws them
 * (BrainScreen.kt's MemoryQueue / LearningFaultBanner) has no wording of its
 * own, so this is the whole phone-side brain.
 */
class MemoryFaultTest {

    private fun obj(json: String): JsonObject = JarvisJson.parseToJsonElement(json).jsonObject

    private val headline = "Jarvis could not check the facts it was about to save: the learning " +
        "model is not on this PC. 2 facts are held back, unsaved, until that check works " +
        "again. This is the check failing, not your facts."

    private val fault = obj(
        "{\"active\": true, \"reason\": \"the learning model is not on this PC\", " +
            "\"headline\": \"$headline\", " +
            "\"count\": 2, \"since\": 1790000000, \"at\": 1790000100, \"tries\": 0, " +
            "\"last_try_at\": null, \"last_result\": \"\", \"recorded\": true, \"why\": \"\"}"
    )

    // ------------------------------------------------------------ words ---

    @Test
    fun `the routes and the one button are the contract's`() {
        assertEquals("/api/memory/fault", MemoryFault.PATH)
        assertEquals("/api/memory/fault/retry", MemoryFault.RETRY_PATH)
        assertEquals("Retry now", MemoryFault.RETRY_LABEL)
        assertTrue(MemoryFault.RETRY_TITLE.contains("approves nothing and saves nothing"))
    }

    // ---------------------------------------------------------- reading ---

    @Test
    fun `an active fault is read with the PC's own sentence, untouched`() {
        val read = requireNotNull(MemoryFault.read(fault))
        assertEquals("the learning model is not on this PC", read.reason)
        assertEquals(headline, read.headline)
        assertEquals(2, read.count)
        assertEquals(0, read.tries)
    }

    @Test
    fun `only an exactly-true active field is a banner`() {
        assertNull(MemoryFault.read(null))
        assertNull(MemoryFault.read(obj("{}")))
        assertNull(MemoryFault.read(obj("""{"active": false, "reason": "r", "headline": "h"}""")))
        // The string "true" is not a JSON boolean, and a fault with no words
        // of its own explains nothing.
        assertNull(MemoryFault.read(obj("""{"active": "true", "reason": "r", "headline": "h"}""")))
        assertNull(MemoryFault.read(obj("""{"active": 1, "reason": "r", "headline": "h"}""")))
        assertNull(MemoryFault.read(obj("""{"active": true, "reason": " ", "headline": ""}""")))
    }

    @Test
    fun `an older PC with only a reason still gets a banner that explains`() {
        val read = requireNotNull(
            MemoryFault.read(
                obj("""{"active": true, "reason": "the learning model is not on this PC"}""")
            )
        )
        assertEquals("the learning model is not on this PC", read.headline)
        // A count that is not a whole number is never a number on screen.
        val counted = requireNotNull(
            MemoryFault.read(obj("""{"active": true, "reason": "r", "count": "9"}"""))
        )
        assertEquals(0, counted.count)
    }

    // ---------------------------------------------------------- retrying ---

    @Test
    fun `a retry that still fails keeps the fault and carries the PC's own words`() {
        val still = "The check still fails: the learning model is not on this PC. " +
            "Nothing was saved or approved."
        val body = "{\"ok\": true, \"cleared\": false, " +
            "\"fault\": {\"active\": true, \"reason\": \"the learning model is not on this PC\", " +
            "\"headline\": \"Jarvis could not check the facts it was about to save\", " +
            "\"count\": 2, \"tries\": 1}, " +
            "\"outcome\": \"$still\"}"
        val reply = MemoryFault.reply(obj(body))
        assertEquals(true, reply.active)
        assertEquals("the learning model is not on this PC", requireNotNull(reply.fault).reason)
        assertEquals(1, requireNotNull(reply.fault).tries)
        assertEquals(still, reply.outcome)
    }

    @Test
    fun `a retry whose check passes clears the banner and keeps the PC's sentence`() {
        val cleared = "The check works again, so the warning is cleared. Nothing was saved " +
            "or approved by this: your facts are still waiting where they were."
        val body = "{\"ok\": true, \"cleared\": true, " +
            "\"fault\": {\"active\": false, \"reason\": \"\", \"count\": 0}, " +
            "\"outcome\": \"$cleared\"}"
        val reply = MemoryFault.reply(obj(body))
        assertEquals(false, reply.active)
        assertNull(reply.fault)
        assertEquals(cleared, reply.outcome)
    }

    @Test
    fun `an answer with no sentence says it could not be read, never a guess`() {
        val reply = MemoryFault.reply(obj("""{"ok": true, "cleared": true}"""))
        assertEquals(false, reply.active)
        assertEquals(MemoryFault.UNREADABLE, reply.outcome)
        // An answer that says neither way leaves the banner as it was.
        assertNull(MemoryFault.reply(obj("""{"ok": true}""")).active)
    }

    // ---------------------------------------------------------- failures ---

    @Test
    fun `a PC without the route says so, and a 503 keeps the PC's own reason`() {
        assertEquals(MemoryFault.MISSING, MemoryFault.readFailure(ApiError.NotFound))
        assertEquals(MemoryFault.NOT_RUNNING, MemoryFault.readFailure(ApiError.NotAvailable))
        assertEquals(
            "The learning pass is not importable.",
            MemoryFault.readFailure(
                ApiError.Server(503, """{"error": "the learning pass is not importable"}""")
            ),
        )
        assertNull(MemoryFault.readFailure(ApiError.Server(500, "")))
    }
}
