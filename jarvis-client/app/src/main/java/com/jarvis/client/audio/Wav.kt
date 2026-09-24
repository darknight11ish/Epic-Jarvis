package com.jarvis.client.audio

import java.io.ByteArrayOutputStream
import kotlin.math.ceil

/**
 * WAV encoding and resampling, done on the phone.
 *
 * `/api/voice/utterance` asks for 16-bit mono PCM at 16 kHz (`audio_in` in
 * /api/voice/status), so the phone sends exactly that. (This used to say the
 * server rejects anything else. It does not: it averages extra channels and
 * passes another rate on to its speech models, which resample. Sending the
 * asked-for format keeps the phone off that path.)
 *
 * Pure functions with no Android types, so they are unit-testable — which
 * matters, because a wrong header or an off-by-one in the decimator produces
 * audio that is *plausible* rather than obviously broken, and the failure would
 * surface as "that didn't sound like you".
 */
object Wav {

    const val SAMPLE_RATE = 16_000
    private const val HEADER_BYTES = 44

    /**
     * Linear-interpolating resample to [SAMPLE_RATE].
     *
     * Linear rather than a windowed sinc: the input is already band-limited by
     * the capture hardware, the ratio is usually an integer (48k → 16k), and
     * the consumer is a voice-print embedder and a speech model rather than a
     * listener. A better kernel would cost more than it buys here.
     *
     * Decimating without any filter would alias, so anything above the target
     * rate is first box-averaged over the decimation window. That is a crude
     * low-pass and it is enough to keep aliased energy out of the band a voice
     * occupies.
     *
     * Two things here were wrong by an amount that is easy to miss and does not
     * look like a bug, because aliasing is not distortion — it is energy folded
     * back down into the speech band as plausible-sounding signal, and the
     * symptom is a voice-print score that is quietly a little worse.
     *
     * The window was `ratio.toInt()`, which truncates: 44.1 kHz decimates by
     * 2.756 and got a 2-sample average, a filter about a third of an octave too
     * wide. And the filter only ran above 1.5x, so 22.05 kHz and 24 kHz — both
     * genuine downsampling, both aliasing everything above 8 kHz — went through
     * completely unfiltered. Measured against the real algorithm, with a 10 kHz
     * tone relative to a 1 kHz tone of the same amplitude: 44.1 kHz went from
     * 0.64 to 0.37, 22.05 kHz from 0.59 to 0.09, 24 kHz from 0.73 to 0.19. A
     * 3 kHz tone — inside the band that matters — loses about 4%.
     *
     * Rounding up rather than to nearest, because the two errors are not
     * symmetric: over-filtering costs a little clarity in the top of the voice
     * band, and under-filtering folds energy in where nothing can remove it.
     */
    fun resample(input: ShortArray, fromRate: Int, toRate: Int = SAMPLE_RATE): ShortArray {
        if (fromRate == toRate || input.isEmpty()) return input
        val ratio = fromRate.toDouble() / toRate

        val src = if (ratio > 1.0) boxFilter(input, ceil(ratio).toInt().coerceAtLeast(2)) else input
        val outLen = ((src.size / ratio)).toInt().coerceAtLeast(1)
        val out = ShortArray(outLen)
        for (i in 0 until outLen) {
            val pos = i * ratio
            val a = pos.toInt()
            val b = (a + 1).coerceAtMost(src.size - 1)
            val frac = pos - a
            if (a >= src.size) break
            out[i] = (src[a] + (src[b] - src[a]) * frac).toInt()
                .coerceIn(Short.MIN_VALUE.toInt(), Short.MAX_VALUE.toInt())
                .toShort()
        }
        return out
    }

    /** A moving average of [window] samples — the anti-alias pass before decimation. */
    private fun boxFilter(input: ShortArray, window: Int): ShortArray {
        if (window <= 1) return input
        val out = ShortArray(input.size)
        var sum = 0L
        for (i in input.indices) {
            sum += input[i]
            if (i >= window) sum -= input[i - window]
            val n = minOf(i + 1, window)
            out[i] = (sum / n).toInt()
                .coerceIn(Short.MIN_VALUE.toInt(), Short.MAX_VALUE.toInt())
                .toShort()
        }
        return out
    }

    /** A 44-byte canonical RIFF header plus little-endian PCM. */
    fun encode(samples: ShortArray, rate: Int = SAMPLE_RATE): ByteArray {
        val dataBytes = samples.size * 2
        val out = ByteArrayOutputStream(HEADER_BYTES + dataBytes)

        fun ascii(s: String) = out.write(s.toByteArray(Charsets.US_ASCII))
        fun le32(v: Int) {
            out.write(v and 0xFF); out.write((v ushr 8) and 0xFF)
            out.write((v ushr 16) and 0xFF); out.write((v ushr 24) and 0xFF)
        }
        fun le16(v: Int) { out.write(v and 0xFF); out.write((v ushr 8) and 0xFF) }

        ascii("RIFF")
        le32(36 + dataBytes)          // everything after this field
        ascii("WAVE")
        ascii("fmt ")
        le32(16)                      // PCM fmt chunk size
        le16(1)                       // format: PCM
        le16(1)                       // channels: mono
        le32(rate)
        le32(rate * 2)                // byte rate: rate * channels * bytesPerSample
        le16(2)                       // block align
        le16(16)                      // bits per sample
        ascii("data")
        le32(dataBytes)
        for (s in samples) { out.write(s.toInt() and 0xFF); out.write((s.toInt() ushr 8) and 0xFF) }
        return out.toByteArray()
    }

    /**
     * The PCM of a WAV, bounded by the `data` chunk's own declared length.
     *
     * This lives here rather than in [Speaker] for the reason at the top of
     * this file: a decoder that reads the wrong bytes does not fail, it
     * produces audio that is merely *wrong*, and the only way to know is to
     * feed it a file whose right answer is known. Two things it does not
     * assume: that `data` starts at byte 44, and that it runs to the end of
     * the file. `LIST`/`INFO` after `data` is common, and reading past the
     * chunk plays the metadata as a click at the end of every sentence.
     */
    fun decode(wav: ByteArray): ShortArray {
        val start = chunkOffset(wav, "data") ?: 44.coerceAtMost(wav.size)
        val declared = if (start >= 8) le32(wav, start - 4) else -1
        val end = if (declared > 0) minOf(start + declared, wav.size) else wav.size
        val n = ((end - start) / 2).coerceAtLeast(0)
        return ShortArray(n) { i ->
            val o = start + i * 2
            ((wav[o].toInt() and 0xFF) or (wav[o + 1].toInt() shl 8)).toShort()
        }
    }

    /**
     * The sample rate from the `fmt ` chunk, found the same way `data` is.
     *
     * Bytes 24..27 are the canonical position and reading them directly was
     * what this did — which contradicted the chunk scan two functions up: an
     * engine that can add a chunk before `data` can add one before `fmt `, and
     * then those four bytes belong to something else. What comes back is not
     * obviously wrong, it is a plausible integer, and it goes straight into
     * `AudioTrack.Builder`, which throws on a rate it cannot serve. So the
     * chunk is located, and a rate outside what any device will accept is
     * refused here rather than by the exception.
     */
    fun rateOf(wav: ByteArray): Int {
        val fmt = chunkOffset(wav, "fmt ") ?: return SAMPLE_RATE
        if (fmt + 8 > wav.size) return SAMPLE_RATE
        val rate = le32(wav, fmt + 4)
        return if (rate in 4_000..192_000) rate else SAMPLE_RATE
    }

    /** Offset of a chunk's payload, or null if the file does not contain it. */
    private fun chunkOffset(wav: ByteArray, want: String): Int? {
        if (wav.size < 12) return null
        var i = 12
        while (i + 8 <= wav.size) {
            val id = String(wav, i, 4, Charsets.US_ASCII)
            val size = le32(wav, i + 4)
            if (id == want) return i + 8
            // Bounds, not just a sign check. The old guard rejected a negative
            // size and claimed that covered walking backwards; it did not.
            // `8 + size` overflows for a large positive size — 0x7FFFFFF8 gives
            // Int.MIN_VALUE — so the cursor jumped to a negative index and the
            // next read threw, which is exactly the backwards walk the comment
            // said was prevented.
            if (size < 0 || size > wav.size - i - 8) return null
            i += 8 + size + (size and 1) // chunks are word-aligned
        }
        return null
    }

    private fun le32(b: ByteArray, o: Int): Int =
        (b[o].toInt() and 0xFF) or ((b[o + 1].toInt() and 0xFF) shl 8) or
            ((b[o + 2].toInt() and 0xFF) shl 16) or ((b[o + 3].toInt() and 0xFF) shl 24)

    /** Root-mean-square of a buffer, 0..1. Drives the face's listening envelope. */
    fun rms(buffer: ShortArray, count: Int = buffer.size): Float {
        if (count <= 0) return 0f
        var sum = 0.0
        for (i in 0 until count) {
            val v = buffer[i] / 32768.0
            sum += v * v
        }
        return kotlin.math.sqrt(sum / count).toFloat().coerceIn(0f, 1f)
    }
}
