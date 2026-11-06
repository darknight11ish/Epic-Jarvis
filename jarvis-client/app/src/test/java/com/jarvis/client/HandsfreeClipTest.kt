package com.jarvis.client

import com.jarvis.client.audio.Wav
import com.jarvis.client.handsfree.HandsfreeClip
import com.jarvis.client.net.Handsfree
import org.junit.Assert.assertArrayEquals
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNotNull
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test

/**
 * The answer clip: collected from the microphone's own buffers, then encoded as
 * the 16 kHz mono WAV the PC asked for.
 *
 * The encoder itself is [Wav]'s and `WavHeaderTest` already holds it. What is
 * new here - and what would be silently wrong in a way that only surfaces as
 * "I didn't catch that" on a real phone - is the COLLECTION: that a partial
 * read lands in the right place, that the 30-second cap truncates at the
 * boundary rather than overshooting (the PC refuses a longer clip rather than
 * truncating it, JARVIS-API section 191.5), and that a clip too short to be a
 * word is refused BEFORE it costs a round trip.
 */
class HandsfreeClipTest {

    /** A ramp, so every sample says which position it was written at. */
    private fun ramp(n: Int, from: Int = 0): ShortArray = ShortArray(n) { (from + it).toShort() }

    @Test
    fun `chunk three lands after chunk two, and a partial read is not padded`() {
        val clip = HandsfreeClip(rate = 16_000, windowSeconds = 10f)
        clip.append(ramp(100, 0), 100)
        clip.append(ramp(100, 1_000), 100)
        // AudioRecord.read returns a count, not a whole buffer: 40 of 100.
        clip.append(ramp(100, 2_000), 40)
        assertEquals(240, clip.captured.size)
        assertArrayEquals(
            (ramp(100, 0) + ramp(100, 1_000) + ramp(40, 2_000)),
            clip.captured,
        )
    }

    @Test
    fun `a read that returns nothing changes nothing`() {
        val clip = HandsfreeClip(rate = 16_000, windowSeconds = 10f)
        clip.append(ramp(100, 0), 100)
        clip.append(ramp(100, 9_000), 0)
        clip.append(ramp(100, 9_000), -3)
        assertEquals(100, clip.captured.size)
    }

    @Test
    fun `the window's cap truncates at the boundary rather than overshooting`() {
        // 1 second, so the numbers in this test are readable: 16,000 samples.
        val clip = HandsfreeClip(rate = 16_000, windowSeconds = 1f)
        assertTrue(clip.append(ShortArray(16_000) { 5 }))
        assertTrue("full", clip.full)
        // A buffer straddling the end: the first 10 are refused, not appended.
        assertTrue(clip.append(ShortArray(10) { 6 }))
        assertEquals(16_000, clip.captured.size)
        assertEquals(1f, clip.seconds, 0.0001f)
    }

    @Test
    fun `the clamp is the PC's 30 seconds, whatever window the caller asks for`() {
        // Section 191.5: a clip over 30 s is REFUSED, never truncated - so the
        // collector must never hold more, even if the answer window is a minute.
        assertEquals(30f, HandsfreeClip.MAX_WINDOW_SECONDS, 0.0001f)
        assertEquals(Handsfree.MAX_CLIP_SEC, HandsfreeClip.MAX_WINDOW_SECONDS.toInt())
        val asked = HandsfreeClip(rate = 16_000, windowSeconds = 60f)
        // 30 s at 16 kHz is the most it will take; one more buffer is refused.
        assertTrue(asked.append(ShortArray(16_000 * 30) { 3 }))
        assertTrue(asked.full)
        assertEquals(16_000 * 30, asked.captured.size)
        assertTrue(asked.append(ShortArray(10) { 4 }))
        assertEquals("nothing past the PC's line", 16_000 * 30, asked.captured.size)
    }

    @Test
    fun `a clip too short to be a word is never encoded`() {
        val clip = HandsfreeClip(rate = 16_000, windowSeconds = 10f)
        // 50 ms: the "hiss" the voice path already refuses below 0.2 s.
        clip.append(ShortArray(800) { 7 })
        assertNull(clip.wav())
        // ...and the floor is the same 0.2 s the recorder uses.
        assertEquals(0.2f, HandsfreeClip.MIN_SECONDS, 0.0001f)
        clip.append(ShortArray(2_800) { 7 })
        assertNotNull("0.225 s is enough", clip.wav())
    }

    @Test
    fun `the encoded clip is the 16 kHz mono WAV the contract asks for`() {
        val rate = 48_000
        val clip = HandsfreeClip(rate = rate, windowSeconds = 2f)
        clip.append(ShortArray(rate) { 100 }, rate) // one second at 48 kHz
        val wav = requireNotNull(clip.wav())
        // The header's own fields, read the way the PC reads them.
        assertEquals("RIFF", String(wav, 0, 4, Charsets.US_ASCII))
        assertEquals("WAVE", String(wav, 8, 4, Charsets.US_ASCII))
        assertEquals("fmt ", String(wav, 12, 4, Charsets.US_ASCII))
        assertEquals(1, le16(wav, 20)) // PCM
        assertEquals(1, le16(wav, 22)) // mono
        // 48 kHz in, 16 kHz out: the resampler is what makes this true.
        assertEquals(16_000, Wav.rateOf(wav))
        assertEquals(16, le16(wav, 34)) // bits per sample
        assertEquals("data", String(wav, 36, 4, Charsets.US_ASCII))
        // A third of 48,000 samples, at two bytes each, plus the 44-byte header.
        val dataBytes = le32(wav, 40)
        assertEquals(wav.size - 44, dataBytes)
        assertEquals(16_000.0, dataBytes / 2.0, 2.0)
    }

    @Test
    fun `base64 is the standard alphabet, so the PC's decoder can read it`() {
        val bytes = byteArrayOf(0x00, 0x01, 0x02, 0x7F, 0xFF.toByte())
        assertEquals("AAECf/8=", HandsfreeClip.base64(bytes))
        // Round trip, with the JDK's own decoder - the two halves of one rule.
        assertArrayEquals(bytes, java.util.Base64.getDecoder().decode(HandsfreeClip.base64(bytes)))
    }

    private fun le16(b: ByteArray, o: Int): Int =
        (b[o].toInt() and 0xFF) or ((b[o + 1].toInt() and 0xFF) shl 8)

    private fun le32(b: ByteArray, o: Int): Int =
        (b[o].toInt() and 0xFF) or ((b[o + 1].toInt() and 0xFF) shl 8) or
            ((b[o + 2].toInt() and 0xFF) shl 16) or ((b[o + 3].toInt() and 0xFF) shl 24)
}
