package com.jarvis.client

import com.jarvis.client.audio.LipSync
import com.jarvis.client.audio.Wav
import kotlinx.serialization.json.Json
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.boolean
import kotlinx.serialization.json.double
import kotlinx.serialization.json.float
import kotlinx.serialization.json.int
import kotlinx.serialization.json.jsonArray
import kotlinx.serialization.json.jsonObject
import kotlinx.serialization.json.jsonPrimitive
import org.junit.Assert.assertArrayEquals
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test
import kotlin.math.abs
import kotlin.math.sin

/**
 * The animals' mouths move the same way on the phone as on the desktop.
 *
 * The two apps cannot share code, so each has its own copy of the lip-sync
 * analysis: `lipsync.js` on the desktop and [LipSync] here.
 * `tools/gen_lipsync.py` runs the JavaScript over the test clips in
 * `src/test/resources/lipsync/` - Jarvis's own Kokoro voice, in its default
 * voice and three animal voices (docs/LIPSYNC.md) - and saves every frame of
 * every mouth track in `lipsync-golden.json`. This checks the Kotlin copy
 * gives the same numbers. If it fails after a change to one copy, make the
 * same change to the other and re-run the generator.
 */
class LipSyncTest {

    private val golden: JsonObject by lazy {
        val text = checkNotNull(javaClass.classLoader?.getResourceAsStream("lipsync-golden.json")) {
            "lipsync-golden.json is missing from test resources - run tools/gen_lipsync.py"
        }.bufferedReader().readText()
        Json.parseToJsonElement(text).jsonObject
    }

    private fun clip(name: String): ByteArray =
        checkNotNull(javaClass.classLoader?.getResourceAsStream("lipsync/$name")) {
            "test clip lipsync/$name is missing"
        }.readBytes()

    private val tol = 1e-3f

    @Test
    fun `the constants match the desktop's`() {
        assertEquals(golden["fps"]!!.jsonPrimitive.int, LipSync.FPS)
        assertEquals(golden["lead_s"]!!.jsonPrimitive.double, LipSync.LEAD_S.toDouble(), 1e-6)
    }

    @Test
    fun `every mouth track matches the desktop's`() {
        val clips = golden["clips"]!!.jsonArray
        assertTrue("the fixture should hold the test clips", clips.size >= 5)
        for (c in clips) {
            val o = c.jsonObject
            val name = o["file"]!!.jsonPrimitive.content
            val wav = clip(name)
            val rate = Wav.rateOf(wav)
            assertEquals("$name: sample rate", o["sampleRate"]!!.jsonPrimitive.int, rate)
            val pcm = Wav.decode(wav)
            assertEquals("$name: samples", o["samples"]!!.jsonPrimitive.int, pcm.size)
            val track = LipSync.analyse(pcm, rate)
            assertEquals("$name: frames", o["n"]!!.jsonPrimitive.int, track.n)
            assertEquals(LipSync.FPS, track.fps)
            for ((key, got) in listOf("level" to track.level, "open" to track.open,
                "wide" to track.wide, "round" to track.round)) {
                val want = o[key]!!.jsonArray
                assertEquals("$name: $key length", want.size, got.size)
                for (i in got.indices) {
                    val w = want[i].jsonPrimitive.float
                    assertTrue("$name: $key[$i] is ${got[i]}, the desktop says $w", abs(got[i] - w) <= tol)
                }
            }
            // sample() at the same moments the desktop was asked about.
            val out = FloatArray(4)
            for (r in o["reads"]!!.jsonArray) {
                val ro = r.jsonObject
                val t = ro["t"]!!.jsonPrimitive.float
                val inside = ro["inside"]!!.jsonPrimitive.boolean
                val want = ro["out"]!!.jsonArray.map { it.jsonPrimitive.float }
                assertEquals("$name: sample($t) inside the clip?", inside, LipSync.sample(track, t, out))
                for (k in 0..3) {
                    assertTrue("$name: sample($t)[$k] is ${out[k]}, the desktop says ${want[k]}",
                        abs(out[k] - want[k]) <= tol)
                }
            }
        }
    }

    @Test
    fun `sample outside the clip, or with no track, is all zeros`() {
        val out = floatArrayOf(9f, 9f, 9f, 9f)
        assertFalse(LipSync.sample(null, 0.3f, out))
        assertArrayEquals(FloatArray(4), out, 0f)

        val track = LipSync.Track(LipSync.FPS, FloatArray(10) { 1f }, FloatArray(10) { 1f },
            FloatArray(10) { 0.5f }, FloatArray(10) { 0.25f })
        out.fill(9f)
        assertFalse("before the lead-in", LipSync.sample(track, -LipSync.LEAD_S - 0.01f, out))
        assertArrayEquals(FloatArray(4), out, 0f)
        out.fill(9f)
        assertFalse("after the last frame", LipSync.sample(track, 0.09f - LipSync.LEAD_S + 0.01f, out))
        assertArrayEquals(FloatArray(4), out, 0f)
        assertTrue("inside", LipSync.sample(track, 0.02f, out))
        assertArrayEquals(floatArrayOf(1f, 1f, 0.5f, 0.25f), out, 1e-6f)

        val empty = LipSync.Track(LipSync.FPS, FloatArray(0), FloatArray(0), FloatArray(0), FloatArray(0))
        assertFalse(LipSync.sample(empty, 0f, out))
    }

    @Test
    fun `sample reads LEAD_S ahead and interpolates between frames`() {
        val n = 20
        val ramp = FloatArray(n) { it / (n - 1f) }
        val track = LipSync.Track(LipSync.FPS, ramp, ramp, FloatArray(n), FloatArray(n))
        val out = FloatArray(4)
        // At playback time t the mouth shows frame (t + LEAD_S) * FPS.
        assertTrue(LipSync.sample(track, 0.0f, out))
        assertEquals(LipSync.LEAD_S * LipSync.FPS / (n - 1f), out[1], 1e-4f)
        // Halfway between frames 7 and 8.
        assertTrue(LipSync.sample(track, 0.075f - LipSync.LEAD_S, out))
        assertEquals(7.5f / (n - 1f), out[0], 1e-4f)
        assertEquals(7.5f / (n - 1f), out[1], 1e-4f)
    }

    @Test
    fun `silence gives a closed mouth, and bad input gives an empty track`() {
        val silent = LipSync.analyse(ShortArray(24_000), 24_000)
        assertEquals(LipSync.FPS, silent.n)
        for (i in 0 until silent.n) {
            assertEquals(0f, silent.level[i], 0f)
            assertEquals(0f, silent.open[i], 0f)
            assertEquals(0f, silent.wide[i], 0f)
            assertEquals(0f, silent.round[i], 0f)
        }
        assertEquals(0, LipSync.analyse(ShortArray(0), 24_000).n)
        assertEquals(0, LipSync.analyse(ShortArray(1000), 0).n)
        // One frame per 10 ms, rounded up, at any rate.
        assertEquals(1, LipSync.analyse(ShortArray(441), 44_100).n)
        assertEquals(2, LipSync.analyse(ShortArray(442), 44_100).n)
        assertEquals(2, LipSync.analyse(ShortArray(320), 16_000).n)
    }

    @Test
    fun `a tone that stops leaves the mouth shut in the silence after it`() {
        // 0.6 s of a vowel-like buzz, then 0.6 s of silence.
        val rate = 24_000
        val pcm = ShortArray(rate * 12 / 10) { i ->
            if (i < rate * 6 / 10) {
                val t = i.toDouble() / rate
                (8000 * (sin(2 * Math.PI * 180 * t) + 0.6 * sin(2 * Math.PI * 720 * t) +
                    0.4 * sin(2 * Math.PI * 1260 * t))).toInt().toShort()
            } else 0
        }
        val track = LipSync.analyse(pcm, rate)
        assertTrue("open while it sounds", track.open[30] > 0.3f)
        for (i in 75 until track.n) assertEquals("closed at frame $i", 0f, track.open[i], 0f)
        for (i in track.level.indices) {
            assertTrue(track.level[i] in 0f..1f && track.open[i] in 0f..1f &&
                track.wide[i] in 0f..1f && track.round[i] in 0f..1f)
        }
    }
}
