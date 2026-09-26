package com.jarvis.client.voice

import java.nio.ByteBuffer
import java.nio.ByteOrder
import kotlin.math.exp
import kotlin.math.max
import kotlin.math.sqrt

/**
 * "Stop" - said while Jarvis is talking, it silences the reply and does
 * nothing else.
 *
 * A second, tiny model on the same sound fingerprint the "hey Jarvis"
 * spotter already computes every 80 ms ([WakeSpotter]'s last 16
 * embeddings): openWakeWord's own head shape, 1,536 -> 32 -> 32 -> 1, trained
 * for the one word "stop" (also "Jarvis, stop", "okay, stop") on synthetic
 * voices. Like the wake word it turns sound into one number and knows no
 * words, so running it on the phone is not speech-to-text. Its numbers are
 * `assets/wakeword/stop_head.bin`; the PC runs the same numbers
 * (`backend/jarvis_stopword.py`), for the desktop app.
 *
 * Stopping speech is harmless, so it acts before any voice check - and it is
 * the ONLY thing that may. "Hey Jarvis" heard while Jarvis talks also stops
 * the reply, and whatever follows goes to the PC and through every check,
 * like any other "hey Jarvis" ([BargeIn]).
 */
class StopHead private constructor(
    private val hidden: Int,
    private val w1: FloatArray, // [1536][hidden]
    private val b1: FloatArray,
    private val g1: FloatArray,
    private val c1: FloatArray,
    private val w2: FloatArray, // [hidden][hidden]
    private val b2: FloatArray,
    private val g2: FloatArray,
    private val c2: FloatArray,
    private val w3: FloatArray, // [hidden]
    private val b3: Float,
) {
    /** The last 16 embeddings (each 96 numbers) -> the chance this is "stop", 0..1. */
    fun score(window: Array<FloatArray>): Float {
        val x = FloatArray(INPUT)
        var k = 0
        for (row in window.takeLast(WakeSpotter.EMB_WINDOW)) for (v in row) if (k < INPUT) x[k++] = v
        val a1 = DoubleArray(hidden) { j -> b1[j].toDouble() }
        for (i in 0 until INPUT) {
            val xi = x[i]
            if (xi == 0f) continue
            val base = i * hidden
            for (j in 0 until hidden) a1[j] += xi * w1[base + j]
        }
        val r1 = relu(layerNorm(a1, g1, c1))
        val a2 = DoubleArray(hidden) { j -> b2[j].toDouble() }
        for (i in 0 until hidden) {
            val base = i * hidden
            for (j in 0 until hidden) a2[j] += r1[i] * w2[base + j]
        }
        val r2 = relu(layerNorm(a2, g2, c2))
        var z = b3.toDouble()
        for (i in 0 until hidden) z += r2[i] * w3[i]
        z = z.coerceIn(-60.0, 60.0)
        return (1.0 / (1.0 + exp(-z))).toFloat()
    }

    private fun layerNorm(a: DoubleArray, g: FloatArray, c: FloatArray): DoubleArray {
        val mean = a.average()
        var v = 0.0
        for (x in a) v += (x - mean) * (x - mean)
        val sd = sqrt(v / a.size + 1e-5)
        return DoubleArray(a.size) { (a[it] - mean) / sd * g[it] + c[it] }
    }

    private fun relu(a: DoubleArray): DoubleArray = DoubleArray(a.size) { max(0.0, a[it]) }

    companion object {
        const val INPUT = WakeSpotter.EMB_WINDOW * WakeSpotter.EMB_SIZE
        const val FILE = "stop_head.bin"

        /**
         * An 80 ms step at or above this is "stop" - backend/jarvis_stopword.py
         * THRESHOLD, the PC's own bar (StopWordTest checks the two agree).
         */
        const val THRESHOLD = 0.5f
        private val MAGIC = "JSTOP1".toByteArray(Charsets.US_ASCII) + byteArrayOf(0, 0)

        /**
         * The file format `backend/jarvis_wakeword.parse_stop_head` reads:
         * 8-byte magic, int32 hidden size, int32 input size, then float32
         * little-endian W1 b1 g1 c1 W2 b2 g2 c2 W3 b3. Throws on anything else.
         */
        fun parse(raw: ByteArray): StopHead {
            require(raw.size >= 16 && raw.copyOfRange(0, 8).contentEquals(MAGIC)) { "not a stop-word head" }
            val buf = ByteBuffer.wrap(raw).order(ByteOrder.LITTLE_ENDIAN)
            buf.position(8)
            val h = buf.int
            val d = buf.int
            require(h in 1..512 && d == INPUT) { "stop-word head has the wrong shape" }
            val floats = d * h + 3 * h + h * h + 3 * h + h + 1
            require(raw.size == 16 + floats * 4) { "stop-word head is the wrong length" }
            fun take(n: Int) = FloatArray(n) { buf.float }.also { a ->
                require(a.all { it.isFinite() }) { "stop-word head holds a non-number" }
            }
            val w1 = take(d * h)
            val b1 = take(h)
            val g1 = take(h)
            val c1 = take(h)
            val w2 = take(h * h)
            val b2 = take(h)
            val g2 = take(h)
            val c2 = take(h)
            val w3 = take(h)
            val b3 = take(1)[0]
            return StopHead(h, w1, b1, g1, c1, w2, b2, g2, c2, w3, b3)
        }
    }
}

/**
 * Interrupting Jarvis while it talks: the rules, with no Android in them
 * (`StopWordTest`).
 */
object BargeIn {
    /** What the listener does with one 80 ms step while Jarvis is speaking. */
    enum class Action { NONE, STOP_SPEAKING, WAKE }

    /**
     * The owner's setting, or the default: ON only where this phone has an
     * echo canceller (Android's `AcousticEchoCanceler.isAvailable()`) -
     * without one the microphone mostly hears Jarvis itself.
     */
    fun enabled(saved: Boolean?, echoCancellerAvailable: Boolean): Boolean = saved ?: echoCancellerAvailable

    /**
     * "Hey Jarvis" wins over "stop" (it stops the speech too, and then
     * listens). "Stop" is not trusted while Jarvis's own recent speech
     * contains the word - its own voice may be what was heard.
     *
     * "Recent", not only "now": [speakingText] is the sentence playing at
     * this moment, but the stop head scores a window that reaches about two
     * seconds back, and it fires only after the quiet that follows the word
     * - by which time the NEXT sentence is usually the one playing. So
     * [recentlySaid] (from [RecentSpeech]) carries every sentence spoken in
     * the last few seconds as well, and any of them saying "stop" is enough
     * to distrust the score.
     */
    fun decide(
        stopScore: Float,
        wakeScore: Float,
        stopThreshold: Float,
        wakeThreshold: Float,
        speakingText: String?,
        recentlySaid: List<String> = emptyList(),
    ): Action = when {
        wakeScore >= wakeThreshold -> Action.WAKE
        stopScore >= stopThreshold && !saysStop(speakingText) && recentlySaid.none { saysStop(it) } ->
            Action.STOP_SPEAKING
        else -> Action.NONE
    }

    /**
     * A word starting with "stop" - "stop", "stops", "stopped", "stopping" -
     * but not one that only has it inside, like "nonstop". Deliberately a
     * little wider than the bare word: the
     * head hears sound, not spelling, and "stopped" starts with the sound it
     * was trained on.
     */
    fun saysStop(text: String?): Boolean = text != null && STOP_WORD.containsMatchIn(text)

    private val STOP_WORD = Regex("(?i)\\bstop")

    /** The switch's line on the Checks screen. */
    fun describe(enabled: Boolean, echoCancellerAvailable: Boolean): String = when {
        enabled && echoCancellerAvailable ->
            "On: while Jarvis talks, this phone listens through its echo canceller. Say " +
                "\"stop\" to silence it, or \"hey Jarvis\" to cut in with something new. Or just " +
                "start talking: Jarvis pauses, and stops if your PC hears it is you."
        enabled ->
            "On, but this phone has no echo canceller, so it may hear Jarvis's own voice " +
                "and stop by mistake."
        echoCancellerAvailable ->
            "Off: while Jarvis talks, this phone does not listen. Turn on to interrupt it " +
                "with \"stop\" or \"hey Jarvis\"."
        else ->
            "Off: this phone has no echo canceller, so it would mostly hear Jarvis's own " +
                "voice. You can still stop a reply from the screen."
    }
}

/**
 * What Jarvis said aloud in the last few seconds, for [BargeIn.decide].
 *
 * WHY A WINDOW. The stop head scores the last 16 embeddings (16 x 80 ms =
 * 1.28 s of steps), and each embedding itself looks back 76 mel frames
 * (0.76 s), so a "stop" in Jarvis's own voice can still move the score about
 * two seconds after it was said - and the head's score peaks after the word,
 * when the next sentence may already be playing. [WINDOW_MS] is that, plus
 * margin for the speaker-to-microphone path. A sentence still playing is
 * always included.
 *
 * Thread-safe: sentences are recorded by the voice turn and read by the
 * barge-in listener on another thread. Times are whatever monotonic clock
 * the caller uses (`SystemClock.elapsedRealtime()` on the phone).
 */
class RecentSpeech(
    private val windowMs: Long = WINDOW_MS,
    private val keep: Int = KEEP,
) {
    private class Said(val text: String, var endedAt: Long?)

    private val said = ArrayDeque<Said>()

    /** A sentence has started playing. */
    @Synchronized
    fun started(text: String) {
        said.addLast(Said(text, null))
        while (said.size > keep) said.removeFirst()
    }

    /** Whatever was playing has finished (or was stopped) at [now]. */
    @Synchronized
    fun ended(now: Long) {
        for (s in said) if (s.endedAt == null) s.endedAt = now
    }

    /** Every sentence playing now, or finished within the window before [now]. */
    @Synchronized
    fun texts(now: Long): List<String> {
        said.removeAll { s -> s.endedAt.let { it != null && now - it > windowMs } }
        return said.map { it.text }
    }

    @Synchronized
    fun clear() {
        said.clear()
    }

    companion object {
        /** ~2 s the head can still hear a word, plus margin. */
        const val WINDOW_MS = 3_000L

        /** More sentences than fit in the window; a bound, not a tuning knob. */
        const val KEEP = 8
    }
}
