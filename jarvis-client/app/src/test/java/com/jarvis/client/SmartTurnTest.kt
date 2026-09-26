package com.jarvis.client

import com.jarvis.client.net.VoiceTurn
import com.jarvis.client.voice.SmartTurn
import com.jarvis.client.voice.TurnEnd
import com.jarvis.client.voice.TurnModel
import com.jarvis.client.voice.TurnSettings
import com.jarvis.client.voice.WhisperFeatures
import kotlinx.serialization.json.Json
import kotlinx.serialization.json.JsonArray
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.double
import kotlinx.serialization.json.int
import kotlinx.serialization.json.jsonArray
import kotlinx.serialization.json.jsonPrimitive
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test
import kotlin.math.PI
import kotlin.math.abs
import kotlin.math.roundToInt
import kotlin.math.sin

/**
 * Smart Turn on the phone: the features the model is fed, and the rule for
 * when a sentence has ended.
 *
 * The features are checked against numbers the PC computed
 * (`backend/jarvis_turn.py features()`, itself checked against Pipecat's own
 * implementation to 0.0 difference) - `smart-turn-golden.json`. The real
 * model is not needed here; it was run separately on a desktop JVM with the
 * plain onnxruntime jar, over the same synthesised clips as the PC, and the
 * probabilities agreed (backend/README.md, "Smart Turn").
 */
class SmartTurnTest {

    private val golden: JsonObject =
        Json.parseToJsonElement(
            requireNotNull(javaClass.classLoader?.getResourceAsStream("smart-turn-golden.json"))
                .readBytes().decodeToString(),
        ) as JsonObject

    /** The signal the golden file was made from, as the phone would hold it. */
    private fun signal(): ShortArray = ShortArray(48_000) { i ->
        val t = i / 16_000.0
        val v = 0.3 * sin(2 * PI * 180 * t) * (0.5 + 0.5 * sin(2 * PI * 3 * t)) +
            0.05 * sin(2 * PI * 1234 * t)
        // float32 first, as numpy did, then to 16-bit.
        (v.toFloat() * 32767f).toDouble().roundToInt().toShort()
    }

    @Test
    fun `the features match the PC's, point by point`() {
        val f = WhisperFeatures.compute(WhisperFeatures.lastWindow(signal()))
        assertEquals(WhisperFeatures.N_MELS * WhisperFeatures.N_FRAMES, f.size)
        var worst = 0.0
        for (p in golden["points"]!!.jsonArray) {
            val a = p as JsonArray
            val m = a[0].jsonPrimitive.int
            val fr = a[1].jsonPrimitive.int
            val want = a[2].jsonPrimitive.double
            worst = maxOf(worst, abs(f[m * WhisperFeatures.N_FRAMES + fr] - want))
        }
        assertTrue("worst difference $worst", worst < 1e-3)
        assertEquals(golden["mean"]!!.jsonPrimitive.double, f.average(), 1e-3)
        assertEquals(golden["max"]!!.jsonPrimitive.double, f.max().toDouble(), 1e-3)
        assertEquals(golden["min"]!!.jsonPrimitive.double, f.min().toDouble(), 1e-3)
    }

    @Test
    fun `shorter audio is padded at the front, longer keeps its end`() {
        val short = ShortArray(100) { 1000 }
        val w = WhisperFeatures.lastWindow(short)
        assertEquals(WhisperFeatures.N_SAMPLES, w.size)
        assertEquals(0f, w[0], 0f)
        assertEquals(1000 / 32768f, w.last(), 1e-6f)

        val long = ShortArray(WhisperFeatures.N_SAMPLES + 500) { if (it < 500) 7 else 9 }
        val lw = WhisperFeatures.lastWindow(long)
        assertEquals(9 / 32768f, lw[0], 1e-9f)
    }

    private class Fixed(val p: Float) : TurnModel {
        var calls = 0
        override fun probability(features: FloatArray): Float {
            calls++
            return p
        }
        override fun close() = Unit
    }

    @Test
    fun `the model's number is read against the threshold, and NaN is not finished`() {
        val x = ShortArray(16_000) { (it % 200 * 50).toShort() }
        assertTrue(SmartTurn(Fixed(0.9f)).complete(x))
        assertFalse(SmartTurn(Fixed(0.2f)).complete(x))
        assertFalse(SmartTurn(Fixed(Float.NaN)).complete(x))
    }

    // ------------------------------------------------------------ the rule

    private val step = 0.08f
    private val loud = 0.2f
    private val quiet = 0.001f

    /** Runs [levels] through a TurnEnd, answering every ASK with [finished]. Returns (seconds, asks). */
    private fun run(end: TurnEnd, levels: List<Float>, finished: (Int) -> Boolean): Pair<Float, Int> {
        var t = 0f
        var asks = 0
        for (l in levels) {
            t += step
            var s = end.push(l, step)
            if (s == TurnEnd.Step.ASK) {
                s = end.answer(finished(asks))
                asks++
            }
            if (s == TurnEnd.Step.END) return t to asks
        }
        return t to asks
    }

    private fun speech(seconds: Float) = List((seconds / step).roundToInt()) { loud }
    private fun silence(seconds: Float) = List((seconds / step).roundToInt()) { quiet }

    @Test
    fun `finished - it ends a moment after the speech, not a second later`() {
        val levels = speech(2f) + silence(3f)
        val (t, asks) = run(TurnEnd(), levels) { true }
        assertEquals(1, asks)
        // 2 s of speech, then the first step at or past 0.2 s of quiet.
        assertTrue("ended at $t", t in 2.2f..2.35f)
    }

    @Test
    fun `not finished - a pause is kept, and the next pause is asked about again`() {
        val levels = speech(1.5f) + silence(1.2f) + speech(1.0f) + silence(3f)
        val (t, asks) = run(TurnEnd(), levels) { it >= 1 } // no the first time, yes the second
        assertEquals(2, asks)
        assertTrue("ended at $t", t in 3.9f..4.05f)
    }

    @Test
    fun `a wrong 'not finished' costs at most the long pause, then it ends anyway`() {
        val levels = speech(1f) + silence(5f)
        val (t, asks) = run(TurnEnd(), levels) { false }
        assertEquals(1, asks)
        assertTrue("ended at $t", abs(t - (1f + TurnEnd.MAX_PAUSE)) < 0.1f)
    }

    @Test
    fun `without the model it is the old fixed pause, and never asks`() {
        val levels = speech(1f) + silence(5f)
        val (t, asks) = run(
            TurnEnd(useModel = false, maxPauseSeconds = TurnEnd.PAUSE_WITHOUT_MODEL),
            levels,
        ) { error("asked with no model") }
        assertEquals(0, asks)
        assertTrue("ended at $t", abs(t - 2f) < 0.1f)
    }

    @Test
    fun `nothing said - it gives up after the grace period, without asking`() {
        val (t, asks) = run(TurnEnd(graceSeconds = 3f), silence(6f)) { true }
        assertEquals(0, asks)
        assertTrue("ended at $t", abs(t - 3f) < 0.1f)
    }

    @Test
    fun `the PC's switch and numbers are followed, inside sane bounds`() {
        val on = VoiceTurn()
        assertTrue(TurnSettings.useModel(on, haveModel = true))
        assertFalse(TurnSettings.useModel(on, haveModel = false))
        assertFalse(TurnSettings.useModel(VoiceTurn(enabled = false), haveModel = true))
        assertEquals(0.5f, TurnSettings.threshold(on), 0f)
        assertEquals(0.95f, TurnSettings.threshold(VoiceTurn(threshold = 7.0)), 0f)
        assertEquals(0.2f, TurnSettings.askAfterSeconds(on), 1e-6f)
        assertEquals(2.0f, TurnSettings.maxPauseSeconds(on), 1e-6f)
        assertEquals(4.0f, TurnSettings.maxPauseSeconds(VoiceTurn(maxPauseMs = 60_000)), 0f)
        // A PC from before Smart Turn sends no `turn`: the defaults are "on, 0.5".
        val old = com.jarvis.client.net.JarvisJson.decodeFromString(
            com.jarvis.client.net.VoiceStatus.serializer(),
            """{"available": true}""",
        )
        assertTrue(old.turn.enabled)
    }

    @Test
    fun `the hard cap holds while someone keeps talking`() {
        val (t, _) = run(TurnEnd(maxSeconds = 5f), speech(20f)) { false }
        assertTrue("ended at $t", abs(t - 5f) < 0.1f)
    }
}
