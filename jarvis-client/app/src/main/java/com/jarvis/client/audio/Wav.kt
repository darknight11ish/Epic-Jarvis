package com.jarvis.client.audio

import java.io.ByteArrayOutputStream

/**
 * WAV encoding and resampling — the two things the server refuses to do.
 *
 * `/api/voice/utterance` takes 16-bit mono PCM at exactly 16 kHz and rejects
 * anything else, deliberately: a resampler on that side would be running on
 * bytes from the network, before the owner gate, in the most exposed code the
 * server has. So it happens here.
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
     * Decimating without any filter would alias, so when downsampling by more
     * than 1.5x the signal is first box-averaged over the decimation window.
     * That is a crude low-pass and it is enough to keep aliased energy out of
     * the band a voice occupies.
     */
    fun resample(input: ShortArray, fromRate: Int, toRate: Int = SAMPLE_RATE): ShortArray {
        if (fromRate == toRate || input.isEmpty()) return input
        val ratio = fromRate.toDouble() / toRate

        val src = if (ratio > 1.5) boxFilter(input, ratio.toInt().coerceAtLeast(2)) else input
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
