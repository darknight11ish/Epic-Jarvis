package com.jarvis.client.handsfree

import com.jarvis.client.audio.Wav
import java.util.Base64

/**
 * One recorded answer, accumulated from the microphone's own buffers and
 * encoded as the WAV the PC asked for.
 *
 * WHY IT IS NOT [`Recorder`][com.jarvis.client.audio.Recorder]. The recorder
 * captures ONE complete utterance and stops on its own terms (a pause, a
 * button, a cap). The hands-free window is a different shape: it is open for a
 * fixed [windowSeconds] whether or not anything is said, it is CLOSED BY THE
 * CLOCK rather than by a pause - a mumbled "confirm" must not keep the
 * microphone open - and whatever it holds when the clock runs out is the clip
 * that goes, or nothing if nothing was heard. It is also started and stopped
 * from a service rather than from a press.
 *
 * WHAT `Wav` STILL DOES: the encoding and the resampling, unchanged. This class
 * only collects. That matters for the tests here: a wrong header or an
 * off-by-one in the decimator is audio that is *plausible* rather than
 * obviously broken (`Wav`'s own doc says so), and `WavHeaderTest` already holds
 * that half. What `HandsfreeClipTest` holds is the collection: that chunk three
 * lands after chunk two, that the cap truncates at the boundary rather than
 * overshooting, and that a clip too short to be a word is refused HERE rather
 * than sent as a round trip the PC answers with "I didn't catch that".
 *
 * PURE - no Android types - so the whole thing runs on the JVM in CI.
 *
 * @param rate the rate the microphone is really recording at; 16 kHz on this
 *   phone because [Recorder][com.jarvis.client.audio.Recorder] asks for it
 *   first, but a device that refuses 16 kHz gives another rate and the
 *   resampler is what makes the upload 16 kHz anyway.
 */
class HandsfreeClip(
    private val rate: Int = Wav.SAMPLE_RATE,
    private val windowSeconds: Float = DEFAULT_WINDOW_SECONDS,
) {
    private val maxSamples: Int = (windowSeconds.coerceIn(1f, 30f) * rate).toInt()
    private var samples: ShortArray = ShortArray(minOf(maxSamples, rate).coerceAtLeast(1_600))
    private var count = 0

    /** Samples held so far, as a copy - the caller cannot change this buffer. */
    val captured: ShortArray get() = samples.copyOf(count)

    /** Seconds held so far, which is what the "too short" rule is about. */
    val seconds: Float get() = count / rate.toFloat()

    /** True when the window is full: the microphone should close now. */
    val full: Boolean get() = count >= maxSamples

    /**
     * Appends one buffer's worth of what the microphone read.
     *
     * [n] is what `AudioRecord.read` returned, and it may be smaller than the
     * buffer - a partial read is normal and is the whole reason this takes a
     * count rather than a whole array. It is never allowed past the cap: a
     * final buffer that straddles the end is truncated, never appended whole,
     * so the clip is exactly [windowSeconds] at most.
     *
     * @return false when the window is now full.
     */
    fun append(buffer: ShortArray, n: Int = buffer.size): Boolean {
        if (n <= 0) return full
        val take = minOf(n, buffer.size, maxSamples - count)
        if (take <= 0) return true
        if (count + take > samples.size) {
            var size = samples.size
            while (size < count + take) size *= 2
            samples = samples.copyOf(minOf(size, maxSamples).coerceAtLeast(count + take))
        }
        System.arraycopy(buffer, 0, samples, count, take)
        count += take
        return full
    }

    /**
     * The clip as the WAV the contract asks for, or null when there is not
     * enough of it to be a word.
     *
     * The floor is [MIN_SECONDS], the same 0.2 s the voice path refuses below
     * ("a gate handed 50ms of hiss produces a number, and that number means
     * nothing" - Recorder.kt). A shorter clip is not uploaded at all: the PC
     * would answer "I didn't catch that", which the phone can say itself,
     * without spending a round trip and without sending 50 ms of a room.
     */
    fun wav(): ByteArray? {
        if (seconds < MIN_SECONDS) return null
        val resampled = Wav.resample(samples.copyOf(count), rate)
        return Wav.encode(resampled, Wav.SAMPLE_RATE)
    }

    companion object {
        /**
         * Ten seconds: long enough to hear the card finish, think, and say
         * "yes, do it" - the owner's own example - and short enough that the
         * microphone is not left open while he walks away.
         */
        const val DEFAULT_WINDOW_SECONDS = 10f

        /** Below this, nothing is sent (see [wav]). */
        const val MIN_SECONDS = 0.2f

        /**
         * Base64 for the contract's `data_b64`.
         *
         * `java.util.Base64` rather than `android.util.Base64`, for one
         * practical reason: the Android class is a stub in JVM unit tests and
         * throws, so a test could not call the encoder at all. This one is in
         * the JDK since API 26 and minSdk here is 33.
         */
        fun base64(bytes: ByteArray): String = Base64.getEncoder().encodeToString(bytes)
    }
}
