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
}
