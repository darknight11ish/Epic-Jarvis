package com.jarvis.client

import com.jarvis.client.voice.BargeIn
import com.jarvis.client.voice.StopHead
import kotlinx.serialization.json.Json
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.double
import kotlinx.serialization.json.int
import kotlinx.serialization.json.jsonArray
import kotlinx.serialization.json.jsonObject
import kotlinx.serialization.json.jsonPrimitive
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test
import java.io.File
import java.nio.ByteBuffer
import java.nio.ByteOrder
import kotlin.math.abs
import kotlin.math.sin

/**
 * "Stop" while Jarvis talks: the phone's copy of the stop head does the PC's
 * arithmetic, and the rules for what a heard word may do.
 *
 * `stop-golden.json` is written by tools/train_stopword.py from the PC's own
 * code (`jarvis_wakeword.stop_probabilities`) over the very bytes shipped in
 * `assets/wakeword/stop_head.bin`; backend/test_stopword.py checks that the
 * asset is jarvis_stopword.py's head, byte for byte.
 */
class StopWordTest {

    private val golden: JsonObject =
        Json.parseToJsonElement(
            requireNotNull(javaClass.classLoader?.getResourceAsStream("stop-golden.json"))
                .readBytes().decodeToString(),
        ) as JsonObject

    /** The shipped asset. Unit tests run from the app module's folder. */
    private fun asset(): ByteArray = File("src/main/assets/wakeword/${StopHead.FILE}").readBytes()

    /** 16 rows of 96, as the spotter hands them over. */
    private fun rows(flat: FloatArray): Array<FloatArray> =
        Array(16) { r -> FloatArray(96) { c -> flat[r * 96 + c] } }

    @Test
    fun `the shipped head is the size the golden file says`() {
        val raw = asset()
        assertEquals(golden["bytes"]!!.jsonPrimitive.int, raw.size)
        StopHead.parse(raw) // does not throw
    }

    @Test
    fun `the phone scores exactly as the PC does`() {
        val head = StopHead.parse(asset())
        for (case in golden["cases"]!!.jsonArray) {
            val k = case.jsonObject["k"]!!.jsonPrimitive.int
            val want = case.jsonObject["p"]!!.jsonPrimitive.double
            val x = FloatArray(StopHead.INPUT) { i -> (2.5 * sin(0.0137 * (i + 1) * (k + 1) + 0.5 * k)).toFloat() }
            val got = head.score(rows(x)).toDouble()
            assertTrue("case $k: phone $got, PC $want", abs(got - want) < 1e-4)
        }
        val real = golden["stop_window"]!!.jsonArray.map { it.jsonPrimitive.double.toFloat() }.toFloatArray()
        val want = golden["stop_p"]!!.jsonPrimitive.double
        val got = head.score(rows(real)).toDouble()
        assertTrue("a real 'stop': phone $got, PC $want", abs(got - want) < 1e-4)
        assertTrue("and it is heard", got >= StopHead.THRESHOLD)
    }

    @Test
    fun `the bar is the PC's bar`() {
        assertEquals(golden["threshold"]!!.jsonPrimitive.double.toFloat(), StopHead.THRESHOLD)
    }

    @Test
    fun `anything that is not a head is refused`() {
        val raw = asset()
        fun refused(bytes: ByteArray) = runCatching { StopHead.parse(bytes) }.isFailure
        assertTrue(refused(ByteArray(0)))
        assertTrue(refused(raw.copyOf().also { it[0] = 'X'.code.toByte() }))
        assertTrue(refused(raw.copyOf(raw.size - 4)))
        assertTrue(refused(raw.copyOf().also { ByteBuffer.wrap(it).order(ByteOrder.LITTLE_ENDIAN).putInt(12, 1535) }))
        val nan = raw.copyOf().also { ByteBuffer.wrap(it).order(ByteOrder.LITTLE_ENDIAN).putFloat(16, Float.NaN) }
        assertTrue(refused(nan))
    }

    @Test
    fun `the default follows the echo canceller, and the owner's choice wins`() {
        assertTrue(BargeIn.enabled(null, echoCancellerAvailable = true))
        assertFalse(BargeIn.enabled(null, echoCancellerAvailable = false))
        assertFalse(BargeIn.enabled(false, echoCancellerAvailable = true))
        assertTrue(BargeIn.enabled(true, echoCancellerAvailable = false))
    }

    @Test
    fun `stop only stops, and hey Jarvis wins`() {
        fun decide(stop: Float, wake: Float, saying: String? = "It is sunny today.") =
            BargeIn.decide(stop, wake, stopThreshold = 0.5f, wakeThreshold = 0.5f, speakingText = saying)
        assertEquals(BargeIn.Action.NONE, decide(0.2f, 0.2f))
        assertEquals(BargeIn.Action.STOP_SPEAKING, decide(0.9f, 0.2f))
        assertEquals(BargeIn.Action.WAKE, decide(0.2f, 0.9f))
        assertEquals(BargeIn.Action.WAKE, decide(0.9f, 0.9f))
        // Jarvis's own sentence says "stop": its own voice may be what was heard.
        assertEquals(BargeIn.Action.NONE, decide(0.9f, 0.2f, "The bus will stop at the corner."))
        assertEquals(BargeIn.Action.STOP_SPEAKING, decide(0.9f, 0.2f, null))
        assertTrue(BargeIn.saysStop("Stopping the timer now."))
        assertFalse(BargeIn.saysStop("The shop is open."))
    }

    @Test
    fun `the switch says what it does in plain words`() {
        assertTrue(BargeIn.describe(true, true).contains("stop"))
        assertTrue(BargeIn.describe(true, false).contains("no echo canceller"))
        assertTrue(BargeIn.describe(false, true).startsWith("Off"))
    }
}
