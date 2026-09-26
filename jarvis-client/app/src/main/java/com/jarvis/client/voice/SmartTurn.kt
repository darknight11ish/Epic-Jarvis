package com.jarvis.client.voice

import com.jarvis.client.net.VoiceTurn
import kotlin.math.PI
import kotlin.math.cos
import kotlin.math.exp
import kotlin.math.ln
import kotlin.math.log10
import kotlin.math.max
import kotlin.math.min
import kotlin.math.sin
import kotlin.math.sqrt

/**
 * "Has the owner finished speaking, or only paused?" - asked when a pause
 * starts, so a sentence is not cut off while someone stops to think, and a
 * finished one is not left waiting a whole second.
 *
 * **This is not speech-to-text.** Smart Turn (Daily / Pipecat, BSD 2-Clause)
 * turns the last few seconds of SOUND into one number: the chance the
 * speaker has finished. It has no vocabulary and produces no words - the same
 * argument [WakeSpotter] makes. Every word is still recognised on the PC,
 * after the owner-voice check.
 *
 * The model is `assets/turn/smart-turn-v3.2-cpu.onnx` (8.7 MB, int8, Whisper
 * Tiny's encoder with a classifier on top), run by the same ONNX Runtime the
 * wake word uses ([OrtTurnModel]). The PC runs the identical file for the
 * desktop app (`backend/jarvis_turn.py`), and this file's features are
 * checked against the PC's numbers (`SmartTurnTest`).
 *
 * Pure Kotlin behind [TurnModel], so the features and the pause rule are unit
 * tested on a plain JVM.
 */
object WhisperFeatures {
    const val SAMPLE_RATE = 16_000
    const val WINDOW_SECONDS = 8
    const val N_SAMPLES = SAMPLE_RATE * WINDOW_SECONDS
    const val N_FFT = 400
    const val HOP = 160
    const val N_MELS = 80
    const val N_FRAMES = N_SAMPLES / HOP // 800
    private const val BINS = N_FFT / 2 + 1

    /** The last 8 s of [samples] (16-bit values), zero-padded at the FRONT, as floats in -1..1. */
    fun lastWindow(samples: ShortArray, count: Int = samples.size): FloatArray {
        val out = FloatArray(N_SAMPLES)
        val take = min(count, N_SAMPLES)
        val from = count - take
        val to = N_SAMPLES - take
        for (i in 0 until take) out[to + i] = samples[from + i] / 32768f
        return out
    }

    /**
     * Whisper's log-mel picture of [window] (exactly [N_SAMPLES] floats), as
     * the model takes it: 80 rows of 800, flattened row by row.
     *
     * The steps, the same as `backend/jarvis_turn.py features()`: scale the
     * waveform to zero mean and unit variance; reflect-pad 200 each side;
     * every 160 samples a 400-sample periodic-Hann frame, its power
     * spectrum, 80 Slaney mel bands; log10 (floored at 1e-10); drop the last
     * frame; clamp to 8 below the maximum; (x + 4) / 4.
     */
    fun compute(window: FloatArray): FloatArray {
        require(window.size == N_SAMPLES) { "want $N_SAMPLES samples" }
        var mean = 0.0
        for (v in window) mean += v
        mean /= N_SAMPLES
        var varSum = 0.0
        for (v in window) {
            val d = v - mean
            varSum += d * d
        }
        // Float, like the reference: it normalises the float32 buffer.
        val sd = sqrt(varSum / N_SAMPLES + 1e-7)
        val x = DoubleArray(N_SAMPLES) { ((window[it] - mean) / sd).toFloat().toDouble() }

        val pad = N_FFT / 2
        fun at(i: Int): Double {
            // numpy's "reflect": the edge sample is not repeated.
            val j = i - pad
            return when {
                j < 0 -> x[-j]
                j >= N_SAMPLES -> x[2 * (N_SAMPLES - 1) - j]
                else -> x[j]
            }
        }

        val out = FloatArray(N_MELS * N_FRAMES)
        val fft = Fft(N_FFT)
        val re = DoubleArray(N_FFT)
        val im = DoubleArray(N_FFT)
        val power = DoubleArray(BINS)
        var top = Double.NEGATIVE_INFINITY
        val logm = DoubleArray(N_MELS * N_FRAMES)
        // N_FRAMES + 1 frames exist; the last is dropped, as the reference does.
        for (f in 0 until N_FRAMES) {
            val start = f * HOP
            for (k in 0 until N_FFT) {
                re[k] = at(start + k) * HANN[k]
                im[k] = 0.0
            }
            fft.transform(re, im)
            for (b in 0 until BINS) power[b] = re[b] * re[b] + im[b] * im[b]
            for (m in 0 until N_MELS) {
                var s = 0.0
                val row = FILTERS[m]
                for (b in row.first until row.first + row.second.size) s += power[b] * row.second[b - row.first]
                val v = log10(max(s, 1e-10))
                logm[m * N_FRAMES + f] = v
                if (v > top) top = v
            }
        }
        val floor = top - 8.0
        for (i in logm.indices) out[i] = ((max(logm[i], floor) + 4.0) / 4.0).toFloat()
        return out
    }

    private val HANN = DoubleArray(N_FFT) { 0.5 - 0.5 * cos(2 * PI * it / N_FFT) }

    private fun hzToMel(f: Double): Double =
        if (f >= 1000.0) 15.0 + ln(f / 1000.0) * (27.0 / ln(6.4)) else 3.0 * f / 200.0

    private fun melToHz(m: Double): Double =
        if (m >= 15.0) 1000.0 * exp((ln(6.4) / 27.0) * (m - 15.0)) else 200.0 * m / 3.0

    /** Each mel band as (first FFT bin, weights from there) - most weights are zero. */
    private val FILTERS: Array<Pair<Int, DoubleArray>> = run {
        val lo = hzToMel(0.0)
        val hi = hzToMel(SAMPLE_RATE / 2.0)
        val edges = DoubleArray(N_MELS + 2) { melToHz(lo + (hi - lo) * it / (N_MELS + 1)) }
        val fftF = DoubleArray(BINS) { (SAMPLE_RATE / 2).toDouble() * it / (BINS - 1) }
        Array(N_MELS) { m ->
            val w = DoubleArray(BINS) { b ->
                val down = (fftF[b] - edges[m]) / (edges[m + 1] - edges[m])
                val up = (edges[m + 2] - fftF[b]) / (edges[m + 2] - edges[m + 1])
                max(0.0, min(down, up)) * (2.0 / (edges[m + 2] - edges[m]))
            }
            val first = w.indexOfFirst { it > 0.0 }.let { if (it < 0) 0 else it }
            val last = w.indexOfLast { it > 0.0 }.let { if (it < 0) 0 else it }
            first to w.copyOfRange(first, last + 1)
        }
    }
}

/**
 * A complex FFT for any length made of small factors - Whisper's 400 is
 * 2 x 2 x 2 x 2 x 5 x 5, which a power-of-two FFT cannot do without changing
 * the answer. Mixed-radix, recursive, in place.
 */
internal class Fft(private val size: Int) {
    // exp(-2 pi i j / size) for every j: every twiddle any level needs is one
    // of these, so no cos/sin runs per frame.
    private val cosT = DoubleArray(size) { cos(-2.0 * PI * it / size) }
    private val sinT = DoubleArray(size) { sin(-2.0 * PI * it / size) }
    private val outRe = DoubleArray(size)
    private val outIm = DoubleArray(size)
    private val scratchRe = DoubleArray(size)
    private val scratchIm = DoubleArray(size)
    private val tRe = DoubleArray(size)
    private val tIm = DoubleArray(size)

    /** In place. Not thread-safe: one per caller. */
    fun transform(re: DoubleArray, im: DoubleArray) {
        require(re.size == size && im.size == size)
        step(re, im, 0, 1, size, 0)
        System.arraycopy(outRe, 0, re, 0, size)
        System.arraycopy(outIm, 0, im, 0, size)
    }

    private fun smallestFactor(n: Int): Int {
        var p = 2
        while (p * p <= n) {
            if (n % p == 0) return p
            p++
        }
        return n
    }

    /** DFT of the n samples in[off + k*stride], written to out[o until o + n]. */
    private fun step(inRe: DoubleArray, inIm: DoubleArray, off: Int, stride: Int, n: Int, o: Int) {
        if (n == 1) {
            outRe[o] = inRe[off]
            outIm[o] = inIm[off]
            return
        }
        val p = smallestFactor(n)
        val m = n / p
        // p sub-transforms of length m, stored one after another. Each is
        // finished (and done with the scratch space) before this level uses it.
        for (r in 0 until p) step(inRe, inIm, off + r * stride, stride * p, m, o + r * m)
        val unitN = size / n // table step for exp(-2 pi i / n)
        val unitP = size / p // table step for exp(-2 pi i / p)
        for (k in 0 until m) {
            for (r in 0 until p) {
                val j = (r * k * unitN) % size
                val yr = outRe[o + r * m + k]
                val yi = outIm[o + r * m + k]
                tRe[r] = yr * cosT[j] - yi * sinT[j]
                tIm[r] = yr * sinT[j] + yi * cosT[j]
            }
            for (q in 0 until p) {
                var sr = 0.0
                var si = 0.0
                for (r in 0 until p) {
                    val j = (r * q * unitP) % size
                    sr += tRe[r] * cosT[j] - tIm[r] * sinT[j]
                    si += tRe[r] * sinT[j] + tIm[r] * cosT[j]
                }
                // To scratch first: out[o + q*m + k] may still be an input
                // for a later k of this same loop.
                scratchRe[q * m + k] = sr
                scratchIm[q * m + k] = si
            }
        }
        System.arraycopy(scratchRe, 0, outRe, o, n)
        System.arraycopy(scratchIm, 0, outIm, o, n)
    }
}

/** The model behind an interface, so the rules here are tested without it. */
interface TurnModel : AutoCloseable {
    /** [WhisperFeatures.compute]'s 80 x 800 floats -> the probability the turn is complete, 0..1. */
    fun probability(features: FloatArray): Float
}

/**
 * The PC's Smart Turn settings (`/api/voice/status` -> `turn`), held inside
 * the range anyone would mean, so one switch governs both listeners.
 */
object TurnSettings {
    /** Use the model: the phone has it loaded AND the owner has not switched it off on the PC. */
    fun useModel(turn: VoiceTurn, haveModel: Boolean): Boolean = haveModel && turn.enabled

    fun threshold(turn: VoiceTurn): Float = turn.threshold.toFloat().coerceIn(0.05f, 0.95f)

    fun askAfterSeconds(turn: VoiceTurn): Float = (turn.askAfterMs / 1000f).coerceIn(0.1f, 1.0f)

    fun maxPauseSeconds(turn: VoiceTurn): Float = (turn.maxPauseMs / 1000f).coerceIn(1.0f, 4.0f)
}

/** Asks [model] about the audio so far. */
class SmartTurn(private val model: TurnModel, private val threshold: Float = THRESHOLD) {

    /** True when the speaker has probably finished. An unusable score is "not finished". */
    fun complete(samples: ShortArray, count: Int = samples.size): Boolean {
        val p = probability(samples, count)
        return p.isFinite() && p >= threshold
    }

    fun probability(samples: ShortArray, count: Int = samples.size): Float =
        model.probability(WhisperFeatures.compute(WhisperFeatures.lastWindow(samples, count)))

    companion object {
        /** The model's own cut-off, as Pipecat uses it and the PC does. */
        const val THRESHOLD = 0.5f
    }
}

/**
 * When to stop recording a sentence, with Smart Turn's help.
 *
 * Fed one step of loudness at a time (the same RMS and floor rules as
 * [WakeClip.EndOfSpeech], so the two agree on what counts as speech):
 *
 *  - Before any speech: wait [graceSeconds], then give up (END).
 *  - Speech, then a pause of [askAfterSeconds] (0.2 s, Pipecat's own
 *    setting): ASK the model once for this pause. "Finished" ends it there
 *    and then - much sooner than the old fixed second of silence.
 *    "Not finished" keeps recording.
 *  - A pause that reaches [maxPauseSeconds] ends it whatever the model said,
 *    so a wrong "not finished" costs at most that long and never hangs.
 *  - [maxSeconds] in all is a hard cap.
 *
 * With [useModel] false (no model on the phone, or switched off on the PC)
 * ASK is never returned; callers then pass [PAUSE_WITHOUT_MODEL] as
 * [maxPauseSeconds], which is exactly the old fixed one-second rule.
 */
class TurnEnd(
    private val graceSeconds: Float = 3.0f,
    private val askAfterSeconds: Float = ASK_AFTER,
    private val maxPauseSeconds: Float = MAX_PAUSE,
    private val maxSeconds: Float = 15f,
    private val useModel: Boolean = true,
    initialFloor: Float = 0.005f,
) {
    enum class Step { LISTEN, ASK, END }

    private var floor = initialFloor
    private var elapsed = 0f
    private var quietFor = 0f
    private var askedThisPause = false
    var heardSpeech = false
        private set

    fun push(level: Float, seconds: Float): Step {
        elapsed += seconds
        val voiced = level >= WakeClip.EndOfSpeech.threshold(floor)
        if (voiced) {
            heardSpeech = true
            quietFor = 0f
            askedThisPause = false
        } else {
            quietFor += seconds
            floor = WakeClip.EndOfSpeech.updateFloor(floor, level)
        }
        return when {
            elapsed >= maxSeconds -> Step.END
            !heardSpeech -> if (elapsed >= graceSeconds) Step.END else Step.LISTEN
            quietFor >= maxPauseSeconds -> Step.END
            useModel && !askedThisPause && quietFor >= askAfterSeconds -> {
                askedThisPause = true
                Step.ASK
            }
            else -> Step.LISTEN
        }
    }

    /** The model's answer to the last [Step.ASK]. */
    fun answer(complete: Boolean): Step = if (complete) Step.END else Step.LISTEN

    companion object {
        /** The pause after which the model is asked. Pipecat's own VAD setting for Smart Turn. */
        const val ASK_AFTER = 0.2f

        /** The longest pause kept inside one sentence when the model says "not finished". */
        const val MAX_PAUSE = 2.0f

        /** The old fixed rule, used when the model is not available. */
        const val PAUSE_WITHOUT_MODEL = 1.0f
    }
}
