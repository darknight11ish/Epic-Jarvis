package com.jarvis.client

import com.jarvis.client.audio.Wav
import org.junit.Assert.assertArrayEquals
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test

/**
 * The header reader, against files whose right answer is known.
 *
 * These came out of [com.jarvis.client.audio.Speaker], where they could not be
 * tested at all — the class needs a `Context`, so the one part of the voice
 * path whose bugs are inaudible-until-they-aren't had no coverage. A decoder
 * reading four bytes from the wrong place does not throw; it returns a
 * plausible integer and the fault arrives later as a click, a burst of noise,
 * or an `AudioTrack` that refuses to build.
 *
 * So the cases below are the non-canonical ones. The canonical file is the
 * easy half and [Wav.encode] already produces it.
 */
class WavHeaderTest {

    private fun le32(v: Int) = byteArrayOf(
        (v and 0xFF).toByte(), ((v ushr 8) and 0xFF).toByte(),
        ((v ushr 16) and 0xFF).toByte(), ((v ushr 24) and 0xFF).toByte(),
    )

    private fun chunk(id: String, body: ByteArray) =
        id.toByteArray(Charsets.US_ASCII) + le32(body.size) + body

    /** A 16-byte PCM `fmt ` payload: format, channels, rate, byte rate, align, bits. */
    private fun fmt(rate: Int) = chunk(
        "fmt ",
        byteArrayOf(1, 0, 1, 0) + le32(rate) + le32(rate * 2) + byteArrayOf(2, 0, 16, 0),
    )

    private fun pcm(samples: ShortArray): ByteArray {
        val out = ByteArray(samples.size * 2)
        samples.forEachIndexed { i, s ->
            out[i * 2] = (s.toInt() and 0xFF).toByte()
            out[i * 2 + 1] = ((s.toInt() ushr 8) and 0xFF).toByte()
        }
        return out
    }

    private fun riff(vararg chunks: ByteArray): ByteArray {
        val body = chunks.reduce { a, b -> a + b }
        return "RIFF".toByteArray(Charsets.US_ASCII) + le32(4 + body.size) +
            "WAVE".toByteArray(Charsets.US_ASCII) + body
    }

    /** What we produce ourselves must survive a round trip exactly. */
    @Test
    fun `encode then decode is the identity`() {
        val samples = ShortArray(512) { (it * 137 - 30000).toShort() }
        val wav = Wav.encode(samples, 16_000)
        assertArrayEquals(samples, Wav.decode(wav))
        assertEquals(16_000, Wav.rateOf(wav))
    }

    /**
     * The case that motivated this. `LIST`/`INFO` after `data` is routine, and
     * decoding to the end of the file plays the metadata as audio — a click on
     * the end of every sentence that sounds like a bad speaker, not a bug.
     */
    @Test
    fun `trailing chunks are not played as audio`() {
        val samples = ShortArray(64) { (it * 400).toShort() }
        val wav = riff(
            fmt(16_000),
            chunk("data", pcm(samples)),
            chunk("LIST", "INFOISFTLavf58.29.100".toByteArray(Charsets.US_ASCII)),
        )
        assertArrayEquals(samples, Wav.decode(wav))
    }

    /**
     * And its mirror. If a chunk can follow `data` one can precede `fmt `, and
     * then bytes 24..27 — where the rate canonically lives — belong to
     * something else entirely.
     */
    @Test
    fun `the rate is found even when fmt is not at byte 24`() {
        val samples = ShortArray(8) { 1000 }
        val wav = riff(
            chunk("JUNK", ByteArray(28) { 0x7F }),
            fmt(48_000),
            chunk("data", pcm(samples)),
        )
        assertEquals(48_000, Wav.rateOf(wav))
        assertArrayEquals(samples, Wav.decode(wav))
    }

    /**
     * A rate no device will serve must be refused here. It goes straight into
     * `AudioTrack.Builder`, which throws — and that throw is outside the guard
     * at the call site, so it would take the coroutine down rather than fall
     * back to something that plays.
     */
    @Test
    fun `an impossible rate falls back rather than being handed on`() {
        val wav = riff(fmt(1), chunk("data", pcm(ShortArray(4))))
        assertEquals(Wav.SAMPLE_RATE, Wav.rateOf(wav))

        val huge = riff(fmt(2_000_000), chunk("data", pcm(ShortArray(4))))
        assertEquals(Wav.SAMPLE_RATE, Wav.rateOf(huge))
    }

    /** Truncated and nonsense input must return something, never loop or throw. */
    @Test
    fun `malformed input is survivable`() {
        assertEquals(0, Wav.decode(ByteArray(0)).size)
        assertEquals(Wav.SAMPLE_RATE, Wav.rateOf(ByteArray(0)))
        assertEquals(Wav.SAMPLE_RATE, Wav.rateOf("RIFF".toByteArray(Charsets.US_ASCII)))

        // A negative chunk size would walk the cursor backwards forever.
        val poisoned = "RIFF".toByteArray(Charsets.US_ASCII) + le32(64) +
            "WAVE".toByteArray(Charsets.US_ASCII) +
            "fmt ".toByteArray(Charsets.US_ASCII) + le32(-8) + ByteArray(16)
        assertEquals(Wav.SAMPLE_RATE, Wav.rateOf(poisoned))
        assertTrue(Wav.decode(poisoned).size >= 0)
    }

    /** An odd-length chunk is padded to an even boundary; the pad is not data. */
    @Test
    fun `odd length chunks are word aligned`() {
        val samples = ShortArray(4) { 2000 }
        val wav = riff(
            chunk("odd ", ByteArray(3) { 1 }) + byteArrayOf(0), // 3 bytes + pad
            fmt(16_000),
            chunk("data", pcm(samples)),
        )
        assertEquals(16_000, Wav.rateOf(wav))
        assertArrayEquals(samples, Wav.decode(wav))
    }

    /**
     * The anti-alias pass, measured rather than assumed.
     *
     * Aliasing is the failure this file's opening comment is about: it is not
     * distortion, it is energy above the target Nyquist folded back down into
     * the speech band as plausible signal, so the only symptom is a voice-print
     * score that is quietly a little worse. Nothing catches that by listening
     * and nothing catches it by reading.
     *
     * A 10 kHz tone is well above 16 kHz's 8 kHz ceiling, so it must come back
     * much quieter than a 1 kHz tone of the same amplitude. The bound differs
     * by rate for a real reason rather than to fit the numbers: when the ratio
     * is a whole number the decimation window is exact and a box filter is
     * simply as good as a box filter gets — 48 kHz lands at 0.51 and 32 kHz at
     * 0.56 and neither can do better without a real kernel. When it is
     * fractional the window has to be rounded up, and rounding up filters
     * harder, so those rates land far lower.
     *
     * Those fractional rates are also exactly the ones that were wrong:
     * truncating the window gave 44.1 kHz a filter a third of an octave too
     * wide, and a 1.5x threshold meant 22.05 kHz and 24 kHz were not filtered
     * at all. They returned 0.64, 0.59 and 0.73 before; they return 0.37, 0.09
     * and 0.19 now.
     */
    @Test
    fun `content above the target nyquist is filtered before decimation`() {
        fun tone(hz: Double, rate: Int) = ShortArray(rate) {
            (0.5 * Short.MAX_VALUE * kotlin.math.sin(2 * Math.PI * hz * it / rate)).toInt().toShort()
        }
        fun leak(rate: Int): Float {
            val low = Wav.rms(Wav.resample(tone(1_000.0, rate), rate))
            val high = Wav.rms(Wav.resample(tone(10_000.0, rate), rate))
            assertTrue("$rate Hz lost the passband as well: 1 kHz came back at $low", low > 0.25f)
            return high / low
        }

        // Whole-number ratios: a box filter's floor.
        for (rate in intArrayOf(48_000, 32_000)) {
            val leaked = leak(rate)
            assertTrue("$rate Hz let 10 kHz through at $leaked of 1 kHz", leaked < 0.62f)
        }

        // Fractional ratios: the window must round up, so these must be well
        // under the bound above. Each of these three was over it.
        for (rate in intArrayOf(44_100, 24_000, 22_050)) {
            val leaked = leak(rate)
            assertTrue(
                "$rate Hz let 10 kHz through at $leaked of 1 kHz — the decimation window " +
                    "is rounding down, or the filter is not running at this ratio at all",
                leaked < 0.45f,
            )
        }
    }
}
