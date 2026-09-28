package com.jarvis.client

import com.jarvis.client.audio.HeardClock
import com.jarvis.client.audio.LipSync
import com.jarvis.client.audio.PresentedFrames
import com.jarvis.client.audio.SpeechEnvelope
import com.jarvis.client.face.Arc
import com.jarvis.client.face.Bindings
import com.jarvis.client.face.FaceFrame
import com.jarvis.client.face.FaceHost
import org.junit.Assert.assertArrayEquals
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNotNull
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test
import kotlin.math.PI
import kotlin.math.abs
import kotlin.math.max
import kotlin.math.sin

/**
 * The phone's half of lip-sync (docs/LIPSYNC.md): the clock that says which
 * moment of a reply the owner is HEARING (not which was last written to the
 * audio queue), the phone's own voice's loudness-only mouth, and the rule
 * the animals live by - no real voice, no mouth movement.
 *
 * All pure: the AudioTrack readings are made up here, so every case the
 * real track can produce - no timestamps yet, a stale one after a pause, a
 * stalled thread - is checked without a phone.
 */
class SpeakerMouthTest {

    private val rate = 24_000
    private val ms = 1_000_000L

    // --- HeardClock -------------------------------------------------------

    @Test
    fun `a playing clip is carried forward on the wall clock`() {
        // 2400 frames (0.1 s) heard at 1 s; 50 ms later, 0.15 s.
        val t = HeardClock.seconds(2_400, 1_000 * ms, 1_050 * ms, rate, running = true, limitFrames = 100_000)
        assertEquals(0.15f, t, 1e-4f)
    }

    @Test
    fun `a paused clip holds where it stopped`() {
        val t = HeardClock.seconds(2_400, 1_000 * ms, 9_000 * ms, rate, running = false, limitFrames = 100_000)
        assertEquals(0.1f, t, 1e-4f)
    }

    @Test
    fun `a reading that stops coming is not carried on forever`() {
        val t = HeardClock.seconds(2_400, 1_000 * ms, 4_000 * ms, rate, running = true, limitFrames = 1_000_000)
        assertEquals(0.1f + HeardClock.MAX_CARRY_S.toFloat(), t, 1e-4f)
    }

    @Test
    fun `nothing is heard that has not been written, and time never runs backwards`() {
        // 4800 frames written = 0.2 s; the carry would say more.
        assertEquals(0.2f, HeardClock.seconds(4_000, 0, 200 * ms, rate, true, 4_800), 1e-4f)
        // A "now" before the reading (two clocks a hair apart) is not a rewind.
        assertEquals(0.1f, HeardClock.seconds(2_400, 1_000 * ms, 990 * ms, rate, true, 100_000), 1e-4f)
        assertEquals(0f, HeardClock.seconds(2_400, 0, 0, 0, true, 100_000), 0f)
    }

    // --- PresentedFrames ----------------------------------------------------

    @Test
    fun `before any timestamp the head stands in`() {
        val p = PresentedFrames(rate)
        p.started(0)
        assertEquals(480L, p.at(10 * ms, tsOk = false, tsFrames = 0, tsNanos = 0, head = 480))
    }

    @Test
    fun `a timestamp is carried to now but never past the head`() {
        val p = PresentedFrames(rate)
        p.started(0)
        // Frame 1000 left the phone at 100 ms; at 120 ms, 1000 + 0.02 * 24000.
        assertEquals(1_480L, p.at(120 * ms, true, 1_000, 100 * ms, head = 3_000))
        val q = PresentedFrames(rate)
        q.started(0)
        assertEquals(1_200L, q.at(120 * ms, true, 1_000, 100 * ms, head = 1_200))
    }

    @Test
    fun `after a pause a stale timestamp is not carried across the pause`() {
        val p = PresentedFrames(rate)
        p.started(0)
        // Timestamps work: 2400 frames between the mixer and the speaker.
        assertEquals(1_000L, p.at(100 * ms, true, 1_000, 100 * ms, head = 3_400))
        // Paused for 5 s, then played again at 5.1 s. The track still offers
        // the timestamp from before the pause; carried forward it would say
        // 5 s of words were heard. The head less the measured gap instead.
        p.started(5_100 * ms)
        assertEquals(1_200L, p.at(5_110 * ms, true, 1_000, 100 * ms, head = 3_600))
        // And a fresh one is used as soon as it arrives.
        assertEquals(1_300L, p.at(5_200 * ms, true, 1_300, 5_200 * ms, head = 3_700))
    }

    @Test
    fun `the mouth never goes backwards when the first real timestamp arrives`() {
        val p = PresentedFrames(rate)
        p.started(0)
        assertEquals(2_000L, p.at(50 * ms, false, 0, 0, head = 2_000))
        // The first timestamp says less was heard than the head suggested.
        assertEquals(2_000L, p.at(60 * ms, true, 500, 60 * ms, head = 2_240))
    }

    // --- SpeechEnvelope (the phone's own voice) ----------------------------

    /** 0.3 s silence, 0.3 s of a loud tone, 0.3 s silence, 16-bit at 16 kHz. */
    private fun clip16(): ByteArray {
        val sr = 16_000
        val n = (sr * 0.9).toInt()
        val out = ByteArray(n * 2)
        for (i in 0 until n) {
            val tone = i >= sr * 0.3 && i < sr * 0.6
            val v = if (tone) (sin(2 * PI * 440 * i / sr) * 0.5 * 32767).toInt() else 0
            out[i * 2] = (v and 0xFF).toByte()
            out[i * 2 + 1] = ((v shr 8) and 0xFF).toByte()
        }
        return out
    }

    private fun toFloat32(pcm16: ByteArray): ByteArray {
        val out = ByteArray(pcm16.size * 2)
        for (i in 0 until pcm16.size / 2) {
            val s = ((pcm16[i * 2].toInt() and 0xFF) or (pcm16[i * 2 + 1].toInt() shl 8)).toShort()
            val bits = java.lang.Float.floatToIntBits(s / 32768f)
            for (k in 0 until 4) out[i * 4 + k] = ((bits ushr (8 * k)) and 0xFF).toByte()
        }
        return out
    }

    private val t0 = 1_000 * ms

    /** The clock time at which [heard] seconds of the voice are being heard. */
    private fun nowFor(heard: Double): Long =
        t0 + ((heard - LipSync.LEAD_S + SpeechEnvelope.OUTPUT_LAG_S) * 1e9).toLong()

    private fun fed(float: Boolean): SpeechEnvelope {
        val e = SpeechEnvelope(16_000)
        val pcm = clip16()
        val bytes = if (float) toFloat32(pcm) else pcm
        // In engine-sized chunks, as onAudioAvailable hands them over.
        var i = 0
        val chunk = if (float) 4_096 else 2_048
        while (i < bytes.size) {
            val part = bytes.copyOfRange(i, minOf(bytes.size, i + chunk))
            if (float) e.addFloat(part, t0) else e.add16(part, t0)
            i += chunk
        }
        return e
    }

    @Test
    fun `the phone's own voice opens the mouth in the loud part only, and never shapes it`() {
        for (float in listOf(false, true)) {
            val e = fed(float)
            assertEquals(90, e.frames)
            val out = FloatArray(4)

            assertTrue(e.sample(nowFor(0.45), out))
            assertTrue("loud part should open the mouth, got ${out[1]} (float=$float)", out[1] > 0.8f)
            assertEquals(0f, out[2], 0f)
            assertEquals(0f, out[3], 0f)

            assertTrue(e.sample(nowFor(0.1), out))
            assertEquals("silence before the tone", 0f, out[1], 0f)

            assertTrue(e.sample(nowFor(0.85), out))
            assertEquals("silence after the tone", 0f, out[1], 1e-3f)
        }
    }

    @Test
    fun `the phone's own voice is on from its first audio until shortly after the last is heard`() {
        val out = FloatArray(4)
        assertFalse("no audio yet is no voice", SpeechEnvelope(16_000).sample(t0, out))

        val e = fed(float = false)
        // Arrived, not heard yet (the output path): a voice, mouth shut.
        assertTrue(e.sample(t0 + 10 * ms, out))
        assertArrayEquals(floatArrayOf(0f, 0f, 0f, 0f), out, 0f)
        // Just after the end: still on, shut.
        assertTrue(e.sample(nowFor(0.95), out))
        // Long after: over.
        assertFalse(e.sample(nowFor(0.9 + SpeechEnvelope.GRACE_S + 0.2), out))
    }

    // --- The face: no real voice, no mouth --------------------------------

    private fun host(steps: Int, state: FaceState, voice: FloatArray?, h: FaceHost = FaceHost()): FaceFrame {
        repeat(steps) {
            h.advance(1f / 60f, state, null, voice?.get(0), Bindings.DEFAULTS, Arc, voiceMouth = voice)
        }
        return h.snapshot()
    }

    @Test
    fun `a typed answer has no mouth, however long it speaks`() {
        // SPEAKING with no voice at all: the reactor faces fall back to their
        // made-up envelope, but the animals get no mouth to move.
        val f = host(120, FaceState.SPEAKING, voice = null)
        assertNull(f.mouth)
        assertTrue("the face itself still moves", f.amp > 0f)
    }

    @Test
    fun `a real voice hands the mouth through, and it goes when the voice does`() {
        val h = FaceHost()
        val f = host(10, FaceState.SPEAKING, floatArrayOf(0.7f, 0.6f, 0.2f, 0.1f), h)
        assertNotNull(f.mouth)
        assertArrayEquals(floatArrayOf(0.6f, 0.2f, 0.1f), f.mouth!!, 0f)
        // Out-of-range and NaN values from a bad sample are clamped, not passed on.
        val g = host(1, FaceState.SPEAKING, floatArrayOf(0.7f, 1.5f, Float.NaN, -1f), h)
        assertArrayEquals(floatArrayOf(1f, 0f, 0f), g.mouth!!, 0f)
        // The voice ends (stop, the end of the clip, a pause): the mouth goes.
        assertNull(host(1, FaceState.SPEAKING, null, h).mouth)
    }

    @Test
    fun `the loudness at the change before last is kept for the animals`() {
        val h = FaceHost()
        host(30, FaceState.IDLE, null, h)
        val loud = host(60, FaceState.SPEAKING, floatArrayOf(0.9f, 0.8f, 0f, 0f), h)
        host(5, FaceState.IDLE, null, h)
        val f = host(1, FaceState.SPEAKING, null, h)
        // Changes: idle->speaking, speaking->idle (at the loud amp), idle->speaking.
        assertEquals(loud.amp, f.prevAmp2, 0.05f)
        assertTrue(f.prevAmp2 > 0.5f)
    }

    @Test
    fun `the error shake is sized from the face, not from the last tap`() {
        val h = FaceHost()
        h.onSize(1_000f)
        var biggest = 0f
        repeat(50) {
            h.advance(1f / 60f, FaceState.ERROR, null, null, Bindings.DEFAULTS, Arc)
            biggest = max(biggest, abs(h.snapshot().shake.x))
        }
        // 1.5% of a 1000 px face; it was 1.5% of ONE pixel until a tap.
        assertTrue("shake was $biggest px", biggest > 5f && biggest <= 15f)
    }
}
