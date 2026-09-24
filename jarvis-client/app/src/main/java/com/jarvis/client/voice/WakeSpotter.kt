package com.jarvis.client.voice

/**
 * Listens for "hey Jarvis" in a stream of 16 kHz audio, and for nothing else.
 *
 * **A keyword spotter is not speech-to-text.** It turns audio into one number
 * — how much the last two seconds sounded like "hey Jarvis" — and has no
 * vocabulary and nothing it could write down. The "a client must not do
 * speech-to-text" rule is about words; this produces none. Every word is
 * still recognised on the PC, after the owner-voice check, exactly as for
 * push-to-talk.
 *
 * The model is openWakeWord's pre-trained "hey jarvis" (three small ONNX
 * files in `assets/wakeword/`, CC BY-NC-SA 4.0 — see the LICENSE there). The
 * PC runs the SAME three files through the same steps
 * (`backend/jarvis_wakeword.py`), so one threshold means one thing on both,
 * and the PC checks every clip this phone sends again before it does
 * anything with it.
 *
 * The streaming is openWakeWord's own `AudioFeatures`, step for step:
 *
 *     every 1280 samples (80 ms):
 *       mel   = melspectrogram(last 1760 samples) / 10 + 2   -> 8 frames x 32
 *       emb   = embedding(last 76 mel frames)                -> 96 numbers
 *       score = wake model(last 16 embeddings)               -> 0..1
 *     the first five scores after a (re)start are ignored.
 *
 * Samples go in as 16-bit VALUES in floats (-32768..32767), not scaled to
 * -1..1: that is what the mel model was exported with.
 *
 * Pure Kotlin behind [WakeModels], so the buffering is unit-tested on a plain
 * JVM (`WakeSpotterTest`) and the real models are only needed on the phone.
 * Not thread-safe; one per stream.
 */
class WakeSpotter(private val models: WakeModels) {

    private var raw = FloatArray(MEL_INPUT)
    private val mel = ArrayDeque<FloatArray>()
    private val feats = ArrayDeque<FloatArray>()
    private var pending = FloatArray(0)
    private var steps = 0

    init {
        reset()
    }

    /** Back to the state after construction: after a clip is sent, say. */
    fun reset() {
        raw = FloatArray(MEL_INPUT)
        pending = FloatArray(0)
        steps = 0
        mel.clear()
        repeat(MEL_WINDOW) { mel.addLast(FloatArray(MEL_BINS) { 1f }) }
        // Upstream primes the embedding buffer from 4 s of faint noise; 4 s of
        // silence does the same job (the first scores are ignored either way)
        // and is the same on every device. The PC does the same.
        val spec = models.melspec(FloatArray(SAMPLE_RATE * 4))
        val windows = ArrayList<Array<FloatArray>>()
        var i = 0
        while (i + MEL_WINDOW <= spec.size) {
            windows.add(Array(MEL_WINDOW) { spec[i + it] })
            i += 8
        }
        feats.clear()
        for (e in models.embedMany(windows).takeLast(EMB_WINDOW)) feats.addLast(e)
    }

    /**
     * Feeds [count] samples (16-bit values). Returns one score per whole
     * 80 ms step completed - possibly none, possibly several.
     *
     * [onWindow], if given, gets each step's 16 x 96 window after the
     * warm-up - the same numbers the wake model just scored - so a second
     * head ([StopHead]) can score them without computing them twice.
     */
    fun feed(
        samples: ShortArray,
        count: Int = samples.size,
        onWindow: ((Array<FloatArray>) -> Unit)? = null,
    ): FloatArray {
        val x = FloatArray(pending.size + count)
        System.arraycopy(pending, 0, x, 0, pending.size)
        for (k in 0 until count) x[pending.size + k] = samples[k].toFloat()
        val whole = (x.size / CHUNK) * CHUNK
        val scores = FloatArray(whole / CHUNK)
        var s = 0
        var off = 0
        while (off < whole) {
            // Slide the 1760-sample window on by one step.
            System.arraycopy(raw, CHUNK, raw, 0, MEL_INPUT - CHUNK)
            System.arraycopy(x, off, raw, MEL_INPUT - CHUNK, CHUNK)
            for (frame in models.melspec(raw)) {
                mel.addLast(frame)
                if (mel.size > MEL_WINDOW) mel.removeFirst()
            }
            feats.addLast(models.embed(mel.toTypedArray()))
            if (feats.size > EMB_WINDOW) feats.removeFirst()
            val window = feats.toTypedArray()
            val score = models.score(window)
            steps++
            scores[s++] = if (steps <= WARMUP_SCORES) 0f else score
            if (steps > WARMUP_SCORES) onWindow?.invoke(window)
            off += CHUNK
        }
        pending = x.copyOfRange(whole, x.size)
        return scores
    }

    companion object {
        const val SAMPLE_RATE = 16_000
        /** 80 ms: the model's own step. */
        const val CHUNK = 1280
        /** 1280 new samples plus 480 of the last: exactly 8 mel frames. */
        const val MEL_INPUT = 1760
        const val MEL_WINDOW = 76
        const val MEL_BINS = 32
        const val EMB_WINDOW = 16
        const val EMB_SIZE = 96
        const val WARMUP_SCORES = 5
    }
}

/** The three models, behind an interface so [WakeSpotter] is testable without them. */
interface WakeModels : AutoCloseable {
    /** [WakeSpotter.MEL_INPUT] (or more) samples -> mel frames, already `/10 + 2`, 32 wide. */
    fun melspec(samples: FloatArray): Array<FloatArray>

    /** 76 frames of 32 -> 96 numbers. */
    fun embed(frames: Array<FloatArray>): FloatArray

    /** Several windows at once. Only the start-up priming uses more than one. */
    fun embedMany(windows: List<Array<FloatArray>>): List<FloatArray> = windows.map { embed(it) }

    /** The last 16 embeddings -> a score, 0..1. */
    fun score(feats: Array<FloatArray>): Float
}

/**
 * What to do with the audio around a detection: the pure half of
 * `WakeWordService`, kept here so it is unit-tested.
 *
 * The clip sent to the PC is the last [PREROLL_SECONDS] before the spotter
 * fired - which holds "hey Jarvis" itself, because a spotter decides a few
 * hundred milliseconds AFTER the phrase ends - plus everything after it until
 * the owner stops talking. The PC needs the phrase in the clip: it checks it
 * again, and a clip without it is dropped there.
 */
object WakeClip {
    const val PREROLL_SECONDS = 2.0f

    /** Keeps the last [capacity] samples. */
    class Ring(val capacity: Int) {
        private val buf = ShortArray(capacity)
        private var next = 0
        private var filled = 0

        fun push(samples: ShortArray, count: Int = samples.size) {
            for (i in 0 until count) {
                buf[next] = samples[i]
                next = (next + 1) % capacity
            }
            filled = minOf(capacity, filled + count)
        }

        /** Oldest first. */
        fun snapshot(): ShortArray {
            val out = ShortArray(filled)
            val start = (next - filled + capacity) % capacity
            for (i in 0 until filled) out[i] = buf[(start + i) % capacity]
            return out
        }

        fun clear() {
            next = 0
            filled = 0
        }
    }

    /**
     * When the owner has finished speaking, from per-step loudness (RMS,
     * 0..1). Loudness only: the PC's Silero VAD trims the result and drops
     * anything that holds no speech, so this errs on the side of a little too
     * much audio rather than a clipped word.
     *
     * @param graceSeconds how long to wait for speech to begin before giving
     *   up - the gap people leave after "hey Jarvis".
     */
    class EndOfSpeech(
        private val graceSeconds: Float = 3.0f,
        private val silenceSeconds: Float = 1.0f,
        private val maxSeconds: Float = 15f,
        initialFloor: Float = 0.005f,
    ) {
        private var floor = initialFloor
        private var elapsed = 0f
        private var quietFor = 0f
        var heardSpeech = false
            private set

        /** Feeds one step of [seconds] at [level]. True when the clip should end. */
        fun push(level: Float, seconds: Float): Boolean {
            elapsed += seconds
            val voiced = level >= threshold(floor)
            if (voiced) {
                heardSpeech = true
                quietFor = 0f
            } else {
                quietFor += seconds
                floor = updateFloor(floor, level)
            }
            return when {
                elapsed >= maxSeconds -> true
                heardSpeech -> quietFor >= silenceSeconds
                else -> elapsed >= graceSeconds
            }
        }

        companion object {
            /** The same numbers the desktop's trigger uses (voice.rs). */
            fun threshold(floor: Float): Float = (floor * 3f).coerceIn(0.006f, 0.05f)

            fun updateFloor(floor: Float, level: Float): Float =
                if (level < floor) floor * 0.7f + level * 0.3f else floor * 0.995f + level * 0.005f
        }
    }
}
