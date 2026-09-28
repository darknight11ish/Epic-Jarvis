package com.jarvis.client.audio

import kotlin.math.max
import kotlin.math.min
import kotlin.math.sqrt

/**
 * "Which moment of this clip is the owner hearing right now?" - the clock
 * the faces' mouths follow (docs/LIPSYNC.md).
 *
 * Pure: no Android types, so the JVM tests can drive it with made-up
 * readings. [Speaker] feeds it what the AudioTrack reports; the face reads
 * the answer every frame.
 *
 * Why not simply "how much has been written": `AudioTrack.write` returns when
 * the samples are QUEUED, and the queue plus the phone's own output path is
 * tens to hundreds of milliseconds (a Bluetooth headset, far more). The old
 * level came from the chunk just written, so the face moved ahead of the
 * voice by exactly that much.
 */
internal object HeardClock {

    /**
     * Longest a reading is carried forward on the wall clock. [Speaker]
     * takes a fresh reading every few tens of milliseconds while it plays;
     * if those stop coming (its thread held up), the face should not run
     * on through words nobody is hearing.
     */
    const val MAX_CARRY_S = 0.25

    /**
     * Seconds of the clip heard at [nowNanos], from a reading of [frames]
     * frames presented at [atNanos].
     *
     * @param running false while the track is paused: the reading is held.
     * @param limitFrames never past this - what has been written so far;
     *   nothing can be heard that has not been handed to the track.
     */
    fun seconds(
        frames: Long,
        atNanos: Long,
        nowNanos: Long,
        rate: Int,
        running: Boolean,
        limitFrames: Long,
    ): Float {
        if (rate <= 0) return 0f
        var f = frames.toDouble()
        if (running) {
            val dt = ((nowNanos - atNanos) / 1e9).coerceIn(0.0, MAX_CARRY_S)
            f += dt * rate
        }
        f = f.coerceIn(0.0, max(0L, limitFrames).toDouble())
        return (f / rate).toFloat()
    }
}

/**
 * Frames actually presented (reaching the speaker), from the two readings an
 * AudioTrack offers. One per clip; called only from [Speaker.play]'s own
 * thread.
 *
 * - `getTimestamp` is the good one: "frame N left the phone at time T". It
 *   is carried forward to now at the clip's rate. It may answer false for
 *   the first moments of a track, and on some devices always.
 * - `playbackHeadPosition` always answers, but it counts what the mixer has
 *   TAKEN, which is ahead of what is heard by the output path's delay. So
 *   while timestamps work, that gap is measured ([lagFrames]) and taken
 *   off the head whenever the head has to stand in.
 *
 * A timestamp older than the last (re)start is stale - after a pause it
 * still describes the moment before the pause, and carrying it forward
 * would jump the mouth ahead by the whole pause - so the head stands in
 * until a fresh one arrives.
 *
 * The answer never goes backwards within a clip (switching from the head to
 * the first real timestamp would otherwise replay a few frames of mouth),
 * and never passes the head (nothing is heard that the mixer has not taken).
 */
internal class PresentedFrames(private val rate: Int) {
    private var startedAt = Long.MIN_VALUE
    private var lagFrames = 0L
    private var last = 0L

    /** The track was told to play (at the start, and after each pause). */
    fun started(nowNanos: Long) {
        startedAt = nowNanos
    }

    /**
     * @param tsOk what `getTimestamp` returned; [tsFrames] and [tsNanos] its
     *   framePosition and nanoTime (ignored when false).
     * @param head `playbackHeadPosition`, read as unsigned.
     * @return frames presented at [nowNanos].
     */
    fun at(nowNanos: Long, tsOk: Boolean, tsFrames: Long, tsNanos: Long, head: Long): Long {
        val fresh = tsOk && rate > 0 && tsNanos >= startedAt && tsFrames >= 0
        val p = if (fresh) {
            val carried = tsFrames + ((nowNanos - tsNanos) / 1e9 * rate).toLong()
            val bounded = min(carried, head)
            lagFrames = max(0L, head - bounded)
            bounded
        } else {
            head - lagFrames
        }
        last = max(last, max(0L, p))
        return last
    }
}

/**
 * Loudness of the phone's OWN voice (Android text-to-speech, the fallback
 * when the PC has none), 100 values a second, built as the audio arrives.
 *
 * That path hands over audio in chunks as it is made, not a whole clip, so
 * [LipSync.analyse] cannot run up front, and there is no track to ask where
 * playback is. What it does have: Android starts playing the first chunk
 * as soon as it has it, and plays on in real time. So "heard" is estimated
 * as the time since the first chunk arrived, less [OUTPUT_LAG_S] for the
 * output path, and never past what has arrived. An estimate, and it says so.
 *
 * The mouth from it opens only (no wide or round): the shape needs the
 * whole clip's analysis, which only the PC's voice gets.
 *
 * One writer (the text-to-speech callback thread) and any number of
 * readers (the face, every frame): the writer fills a value and then
 * publishes the count through a volatile, the readers read the count first,
 * so a reader never sees a slot that is not written. No locks.
 */
internal class SpeechEnvelope(
    private val rate: Int,
    private val channels: Int = 1,
) {
    @Volatile private var values = FloatArray(256)
    @Volatile private var count = 0

    /** When the first audio arrived (System.nanoTime), 0 until then. */
    @Volatile var firstAtNanos = 0L
        private set

    private val block = max(1, rate / LipSync.FPS) * max(1, channels)
    private var sum = 0.0
    private var inBlock = 0
    private var peak = PEAK_FLOOR
    private var env = 0.0

    /** Frames (1/100 s each) received so far. */
    val frames: Int get() = count

    /** 16-bit little-endian PCM, [len] bytes of [bytes]. */
    fun add16(bytes: ByteArray, nowNanos: Long, len: Int = bytes.size) {
        if (len < 2) return
        if (firstAtNanos == 0L) firstAtNanos = nowNanos
        var i = 0
        while (i + 1 < len) {
            val s = ((bytes[i].toInt() and 0xFF) or (bytes[i + 1].toInt() shl 8)).toShort()
            push(s / 32768.0)
            i += 2
        }
    }

    /** 32-bit float little-endian PCM (ENCODING_PCM_FLOAT). */
    fun addFloat(bytes: ByteArray, nowNanos: Long, len: Int = bytes.size) {
        if (len < 4) return
        if (firstAtNanos == 0L) firstAtNanos = nowNanos
        var i = 0
        while (i + 3 < len) {
            val bits = (bytes[i].toInt() and 0xFF) or
                ((bytes[i + 1].toInt() and 0xFF) shl 8) or
                ((bytes[i + 2].toInt() and 0xFF) shl 16) or
                ((bytes[i + 3].toInt() and 0xFF) shl 24)
            val v = java.lang.Float.intBitsToFloat(bits).toDouble()
            push(if (v.isFinite()) v.coerceIn(-1.0, 1.0) else 0.0)
            i += 4
        }
    }

    private fun push(v: Double) {
        sum += v * v
        if (++inBlock < block) return
        val rms = sqrt(sum / inBlock)
        sum = 0.0
        inBlock = 0
        if (rms > peak) peak = rms
        val x = (rms / peak).coerceIn(0.0, 1.0)
        // The same attack/release shape as LipSync's level: quick up, slower down.
        env += (x - env) * (if (x > env) ATTACK else RELEASE)
        append(env.toFloat())
    }

    private fun append(v: Float) {
        val n = count
        if (n >= MAX_FRAMES) return
        var a = values
        if (n >= a.size) {
            a = a.copyOf(min(MAX_FRAMES, a.size * 2))
            values = a
        }
        a[n] = v
        count = n + 1
    }

    /**
     * Level and mouth at [nowNanos] into [out] (level, open, wide, round -
     * the [LipSync.sample] layout). False (zeros) before any audio arrived,
     * and once everything that arrived was heard more than [GRACE_S] ago
     * (the voice is over, whatever the engine has not yet said); true with
     * zeros in the gaps before and just after it is heard.
     */
    fun sample(nowNanos: Long, out: FloatArray): Boolean {
        out[0] = 0f; out[1] = 0f; out[2] = 0f; out[3] = 0f
        val n = count
        val a = values
        val t0 = firstAtNanos
        if (t0 == 0L || n == 0) return false
        val heard = (nowNanos - t0) / 1e9 - OUTPUT_LAG_S
        val f = (heard + LipSync.LEAD_S) * LipSync.FPS
        if (f > n - 1 + GRACE_S * LipSync.FPS) return false
        if (f < 0.0 || f > n - 1) return true
        val i = f.toInt()
        val j = min(i + 1, n - 1)
        val u = (f - i).toFloat()
        val level = a[i] + (a[j] - a[i]) * u
        out[0] = level
        out[1] = openFrom(level)
        return true
    }

    companion object {
        /**
         * Android's own output path, from its first chunk to the speaker: a
         * typical figure, not a measurement - this path has no timestamps.
         */
        const val OUTPUT_LAG_S = 0.08

        /** How long after the last audio heard the voice still counts as on. */
        const val GRACE_S = 0.5

        /** Ten minutes: far past any sentence; beyond it the mouth just closes. */
        const val MAX_FRAMES = 60_000

        /** Quieter than this is not "the loudest yet" - background hiss is not scaled up. */
        const val PEAK_FLOOR = 0.02

        const val ATTACK = 0.6
        const val RELEASE = 0.15

        /** Mouth opening from loudness alone: closed in near-silence, full at loud. */
        fun openFrom(level: Float): Float = ((level - 0.08f) / 0.7f).coerceIn(0f, 1f)
    }
}
