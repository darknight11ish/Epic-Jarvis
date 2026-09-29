package com.jarvis.client.audio

import kotlin.math.PI
import kotlin.math.abs
import kotlin.math.ceil
import kotlin.math.cos
import kotlin.math.exp
import kotlin.math.floor
import kotlin.math.ln
import kotlin.math.log10
import kotlin.math.max
import kotlin.math.min
import kotlin.math.pow
import kotlin.math.sin
import kotlin.math.sqrt

/**
 * Lip-sync for the faces: turns one spoken reply (the whole WAV, analysed
 * before it plays) into a "mouth track" - [FPS] frames a second of
 *  - `level`: how loud, 0..1, smoothed - every face's sound level;
 *  - `open`: how far the mouth is open (0 = closed: pauses, m/b/p);
 *  - `wide`: lips spread (ee, i, s - teeth showing);
 *  - `round`: lips rounded (oo, oh, w).
 * The face reads the track at the AudioTrack's own playback position (plus
 * [LEAD_S]), so the mouth stays in step with what is heard. Everything
 * happens on the phone; nothing is sent anywhere.
 *
 * A line-for-line copy of the desktop's `jarvis-desktop/src/lipsync.js`.
 * `tools/gen_lipsync.py` runs the JavaScript over the test clips in
 * `src/test/resources/lipsync/` and saves `lipsync-golden.json`;
 * `LipSyncTest` fails if this copy gives different numbers. Change both
 * together. How it works and how it was measured: `docs/LIPSYNC.md`.
 *
 * Pure Kotlin, no Android types, so it runs in plain unit tests. Doubles
 * inside (as JavaScript), floats only in the finished track.
 */
object LipSync {

    const val FPS = 100

    /**
     * How far ahead of the audio clock the mouth is read. Lips move slightly
     * before the sound they make, and viewers accept a mouth that is early
     * far more readily than one that is late (docs/LIPSYNC.md, "Why 50 ms").
     */
    const val LEAD_S = 0.05f

    /**
     * The mouth (open, wide, round - not the level) fades in over the first
     * [ONSET_S] of each clip's playback. The lead means t = 0 already reads
     * 50 ms in, and Kokoro often starts sounding 10-50 ms into a clip:
     * without this the mouth jumped from shut to a quarter open in one frame
     * at the start of a sentence. They also fade out over the track's last
     * [ONSET_S] ([sample]). The desktop's `sample()` does the same.
     */
    const val ONSET_S = 0.05f

    class Track(
        val fps: Int,
        val level: FloatArray,
        val open: FloatArray,
        val wide: FloatArray,
        val round: FloatArray,
    ) {
        val n: Int get() = level.size
    }

    /**
     * Where the phrases end, worked out before they are heard - the desktop's
     * `JarvisLipSync.phraseEnds` (see its note). The talking gestures land on
     * the end of one of Jarvis's phrases, and the whole clip is read before it
     * plays, so from its own loudness ([Track.level]) the same rules as the
     * live finder (`CritterPose.pauseStep`) can find the ends ahead of time: a
     * stretch of [PhraseRule.QUIET] seconds under [PhraseRule.OFF] after at
     * least [PhraseRule.TALK_MIN] seconds over [PhraseRule.ON], and never
     * closer than [PhraseRule.GAP] to the one before. Returns the seconds
     * (into the clip, on the clock [sample] reads) where each phrase's sound
     * STOPS - the start of that quiet stretch - plus the clip's own end when
     * its sound runs right up to it. Counted in whole frames.
     */
    object PhraseRule {
        const val ON = 0.10f
        const val OFF = 0.05f
        const val TALK_MIN = 0.6f
        const val QUIET = 0.05f
        const val GAP = 2.0f
    }
    fun phraseEnds(track: Track?): FloatArray {
        if (track == null || track.n <= 0 || track.fps <= 0) return FloatArray(0)
        val fps = track.fps
        val quietN = Math.round(PhraseRule.QUIET * fps)
        val talkN = Math.round(PhraseRule.TALK_MIN * fps)
        val gapN = Math.round(PhraseRule.GAP * fps)
        val out = ArrayList<Float>()
        var talk = 0
        var quiet = 0
        var last = -1_000_000_000
        for (i in 0 until track.n) {
            val lv = track.level[i]
            if (lv >= PhraseRule.ON) { talk++; quiet = 0 } else if (lv <= PhraseRule.OFF) quiet++
            if (quiet >= quietN && talk > 0) {
                if (talk >= talkN && i - last >= gapN) { out.add((i - quietN + 1).toFloat() / fps); last = i }
                talk = 0
            }
        }
        // Sound right up to the clip's last frame: the clip's end is a phrase end.
        if (talk >= talkN && track.n - last >= gapN) out.add(track.n.toFloat() / fps)
        return out.toFloatArray()
    }

    /** 16-bit mono PCM, as [Speaker] plays it. */
    fun analyse(pcm: ShortArray, sampleRate: Int): Track =
        analyse(FloatArray(pcm.size) { pcm[it] / 32768f }, sampleRate)

    /**
     * Reads the track at [tSeconds] of playback (+ [LEAD_S]), linearly
     * between frames, into `out[0..3]` = level, open, wide, round (the mouth
     * three faded in over the first [ONSET_S] of the clip, and out over the
     * track's last [ONSET_S]). Outside the
     * clip (or no track) it writes zeros and returns false.
     */
    fun sample(track: Track?, tSeconds: Float, out: FloatArray): Boolean {
        out[0] = 0f; out[1] = 0f; out[2] = 0f; out[3] = 0f
        if (track == null || track.n == 0) return false
        val f = (tSeconds.toDouble() + LEAD_S_D) * track.fps
        if (!(f >= 0.0) || f > track.n - 1) return false
        val i = floor(f).toInt()
        val u = (f - i).toFloat()
        val j = min(i + 1, track.n - 1)
        val td = tSeconds.toDouble()
        // ...and fades out over the track's last ONSET_S: past the last frame
        // the mouth is shut, and a clip whose sound runs (nearly) to its end
        // used to snap from wide open to shut in one frame there. As lipsync.js.
        val start = if (td >= ONSET_S_D) 1.0 else if (td > 0.0) td / ONSET_S_D else 0.0
        val end = (track.n - 1 - f) / (ONSET_S_D * track.fps)
        val g = min(start, end).toFloat()
        out[0] = track.level[i] + (track.level[j] - track.level[i]) * u
        out[1] = (track.open[i] + (track.open[j] - track.open[i]) * u) * g
        out[2] = (track.wide[i] + (track.wide[j] - track.wide[i]) * u) * g
        out[3] = (track.round[i] + (track.round[j] - track.round[i]) * u) * g
        return true
    }

    // ---- Mouth shapes carried inside the WAV ---------------------------------

    /**
     * Frames by which the PC's mouth track and the clip's own may differ in
     * length and still be [merge]d (30 ms).
     */
    const val MERGE_SLACK = 3

    /**
     * The mouth track for one clip [Speaker] is about to play: the clip's own
     * analysis ([analyse]), with open, wide and round taken instead from the
     * mouth shapes the PC put in the WAV, when it did ([Wav.mouthChunk],
     * [mouthFrom], [merge]). A clip without them, or with ones that are in
     * any way wrong, gets exactly the analysis - a fault in the chunk costs
     * the better mouth, never the mouth.
     */
    fun forClip(wav: ByteArray, pcm: ShortArray, sampleRate: Int): Track {
        val audio = analyse(pcm, sampleRate)
        val mouth = try {
            Wav.mouthChunk(wav)?.let { mouthFrom(it) }
        } catch (e: RuntimeException) {
            null
        }
        return merge(audio, mouth)
    }

    private val FIELD = Regex("[A-Za-z0-9_]+=[^;]*")
    private val PACKED = Regex("([0-9]{1,4}):([A-Za-z0-9+/]*)(={0,2})")
    private const val B64 = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/"

    /**
     * The track in a "jmth" chunk's payload ("v1;src=kokoro;" + a packed
     * track), or null for anything else: another version, a field that is not
     * `key=value`, or a packed track [unpack] refuses. Trailing NULs and
     * spaces (padding) are not data. The desktop's `mouthFrom` is the same.
     */
    fun mouthFrom(text: String): Track? {
        val t = text.trimEnd { it == '\u0000' || it == '\t' || it == '\n' || it == '\r' || it == ' ' }
        val parts = t.split(";")
        if (parts.size < 2 || parts[0] != "v1") return null
        for (i in 1 until parts.size - 1) if (!FIELD.matches(parts[i])) return null
        return unpack(parts[parts.size - 1])
    }

    /**
     * A packed track (the desktop's `pack()`: "<fps>:" + base64 of 4 bytes a
     * frame - level, open, wide, round, each 0..255), or null unless it is
     * well-formed, at [FPS] frames a second, whole frames, at least one.
     */
    fun unpack(packed: String): Track? {
        val m = PACKED.matchEntire(packed) ?: return null
        val body = m.groupValues[2]
        val pad = m.groupValues[3].length
        val chars = body.length + pad
        if (m.groupValues[1].toInt() != FPS || chars == 0 || chars % 4 != 0) return null
        val len = chars / 4 * 3 - pad
        if (len % 4 != 0) return null
        val bytes = IntArray(len)
        var j = 0
        var i = 0
        while (i < body.length) {
            fun at(k: Int) = if (k < body.length) B64.indexOf(body[k]) else 0
            val v = (at(i) shl 18) or (at(i + 1) shl 12) or (at(i + 2) shl 6) or at(i + 3)
            if (j < len) bytes[j++] = (v shr 16) and 255
            if (j < len) bytes[j++] = (v shr 8) and 255
            if (j < len) bytes[j++] = v and 255
            i += 4
        }
        val n = len / 4
        return Track(
            FPS,
            FloatArray(n) { (bytes[it * 4] / 255.0).toFloat() },
            FloatArray(n) { (bytes[it * 4 + 1] / 255.0).toFloat() },
            FloatArray(n) { (bytes[it * 4 + 2] / 255.0).toFloat() },
            FloatArray(n) { (bytes[it * 4 + 3] / 255.0).toFloat() },
        )
    }

    /**
     * A track with `level` from the clip's own sound ([audio]) and open, wide
     * and round from the PC's mouth shapes ([mouth]) - only when both are at
     * [FPS] and their lengths agree within [MERGE_SLACK] frames; otherwise
     * [audio] as it is. Frames past the end of a shorter [mouth] are closed.
     */
    fun merge(audio: Track, mouth: Track?): Track {
        if (mouth == null || audio.fps != FPS || mouth.fps != FPS || mouth.n <= 0 ||
            abs(audio.n - mouth.n) > MERGE_SLACK
        ) return audio
        val n = audio.n
        fun take(ch: FloatArray) = FloatArray(n) { if (it < mouth.n) ch[it].coerceIn(0f, 1f) else 0f }
        return Track(FPS, audio.level, take(mouth.open), take(mouth.wide), take(mouth.round))
    }

    // The same number JavaScript uses (0.05 as a double, not 0.05f widened).
    private const val LEAD_S_D = 0.05
    private const val ONSET_S_D = 0.05

    private fun clamp01(x: Double) = if (x < 0.0) 0.0 else if (x > 1.0) 1.0 else x
    private fun smooth01(a: Double, b: Double, x: Double): Double {
        val t = clamp01((x - a) / (b - a))
        return t * t * (3 - 2 * t)
    }

    /**
     * Power spectrum of N real samples via one complex FFT of N/2 points (the
     * usual even/odd packing), bins 0..N/2. Iterative radix-2, in place.
     */
    private class Spectrum(private val nn: Int) {
        private val m = nn shr 1
        private val cosM = DoubleArray(m shr 1) { cos(2 * PI * it / m) }
        private val sinM = DoubleArray(m shr 1) { sin(2 * PI * it / m) }
        private val cosN = DoubleArray(m + 1) { cos(2 * PI * it / nn) }
        private val sinN = DoubleArray(m + 1) { sin(2 * PI * it / nn) }
        private val rev: IntArray
        private val zr = DoubleArray(m)
        private val zi = DoubleArray(m)

        init {
            var bits = 0
            while ((1 shl bits) < m) bits++
            rev = IntArray(m) { i ->
                var r = 0
                for (j in 0 until bits) r = r or (((i shr j) and 1) shl (bits - 1 - j))
                r
            }
        }

        fun power(x: DoubleArray, pw: DoubleArray) {
            for (i in 0 until m) {
                val j = rev[i]; zr[j] = x[2 * i]; zi[j] = x[2 * i + 1]
            }
            var size = 2
            while (size <= m) {
                val half = size shr 1
                val step = m / size
                var i = 0
                while (i < m) {
                    for (k in 0 until half) {
                        val wr = cosM[k * step]
                        val wi = -sinM[k * step]
                        val a = i + k
                        val b = a + half
                        val xr = zr[b] * wr - zi[b] * wi
                        val xi = zr[b] * wi + zi[b] * wr
                        zr[b] = zr[a] - xr; zi[b] = zi[a] - xi
                        zr[a] += xr; zi[a] += xi
                    }
                    i += size
                }
                size = size shl 1
            }
            for (k in 0..m) {
                val ka = if (k == m) 0 else k
                val mk = if (k == 0) 0 else m - k
                val er = (zr[ka] + zr[mk]) * 0.5
                val ei = (zi[ka] - zi[mk]) * 0.5
                val or = (zi[ka] + zi[mk]) * 0.5
                val oi = -(zr[ka] - zr[mk]) * 0.5
                val c = cosN[k]
                val s = sinN[k]
                val xr = er + c * or + s * oi
                val xi = ei + c * oi - s * or
                pw[k] = xr * xr + xi * xi
            }
        }
    }

    private fun db(e: Double) = 10 * log10(e + 1e-12)

    // Quarter-octave bands from BAND_LO Hz: band j covers
    // BAND_LO * 2^(j/4) .. BAND_LO * 2^((j+1)/4).
    private const val BAND_LO = 75.0
    private const val NB = 29
    private const val LN2 = 0.6931471805599453 // JavaScript's Math.LN2
    private fun bandPos(hz: Double) = 4 * ln(hz / BAND_LO) / LN2

    private class Features(val n: Int, val all: DoubleArray, val bands: DoubleArray)

    // Stage 1: per-frame broadband level (dB) and quarter-octave band powers
    // of the pre-emphasised, Hann-windowed frame (~25 ms, centred on the
    // frame's time). Frames far below everything else skip the FFT.
    private fun features(samples: FloatArray, sr: Int): Features {
        val len = samples.size
        val n = if (len > 0) ((len.toLong() * FPS + sr - 1) / sr).toInt() else 0
        var nn = 128
        val target = 0.025 * sr
        while (nn < 2048 && nn * 1.4142 < target) nn *= 2
        val half = nn shr 1
        val spectrum = Spectrum(nn)
        val fr = DoubleArray(nn)
        val p = DoubleArray(half + 1)
        val w = DoubleArray(nn)
        var wsum = 0.0
        for (k in 0 until nn) {
            w[k] = 0.5 - 0.5 * cos(2 * PI * k / nn); wsum += w[k] * w[k]
        }
        val bandOf = IntArray(half + 1) { k ->
            val hz = k.toDouble() * sr / nn
            val j = if (hz >= BAND_LO) floor(bandPos(hz)).toInt() else -1
            if (j in 0 until NB) j else -1
        }
        val all = DoubleArray(n)
        val bands = DoubleArray(n * NB)
        for (i in 0 until n) {
            val start = ((i.toLong() * sr) / FPS).toInt() - half
            var e = 0.0
            for (k in 0 until nn) {
                val idx = start + k
                val x = if (idx in 0 until len) samples[idx].toDouble() else 0.0
                val pv = if (idx in 1..len) samples[idx - 1].toDouble() else 0.0
                val wx = w[k] * x
                e += wx * wx
                fr[k] = w[k] * (x - 0.97 * pv)
            }
            all[i] = db(e / wsum)
            if (all[i] < -100) continue
            spectrum.power(fr, p)
            val o = i * NB
            for (k in 1..half) if (bandOf[k] >= 0) bands[o + bandOf[k]] += p[k] / wsum
        }
        return Features(n, all, bands)
    }

    // Power between band positions x0..x1 (fractional band indices).
    private fun bandSum(b: DoubleArray, o: Int, x0: Double, x1: Double): Double {
        var s = 0.0
        val j0 = max(0, floor(x0).toInt())
        val j1 = min(NB - 1, floor(x1).toInt())
        for (j in j0..j1) {
            val a = if (x0 > j) x0 else j.toDouble()
            val bb = if (x1 < j + 1) x1 else (j + 1).toDouble()
            if (bb > a) s += b[o + j] * (bb - a)
        }
        return s
    }

    private fun percentile(arr: DoubleArray, count: Int, q: Double): Double {
        if (count <= 0) return 0.0
        val a = arr.copyOf(count)
        a.sort()
        return a[floor(q * (count - 1)).toInt()]
    }

    // Smoothing without delay: a one-pole filter run forward (coefficient af)
    // and then backward (ab). A smaller backward coefficient (slower) spreads
    // each change a little EARLIER in time - anticipation, as real lips do.
    private fun smoothFB(x: DoubleArray, af: Double, ab: Double) {
        val n = x.size
        if (n == 0) return
        var y = x[0]
        for (i in 0 until n) { y += (x[i] - y) * af; x[i] = y }
        y = x[n - 1]
        for (i in n - 1 downTo 0) { y += (x[i] - y) * ab; x[i] = y }
    }

    private fun coef(ms: Double) = 1 - exp(-1000.0 / FPS / ms)

    // The tuning, measured on Jarvis's real voice (Kokoro) in its default and
    // three animal voices - docs/LIPSYNC.md has the numbers. Hz for band
    // edges, dB for levels and thresholds, ms for smoothing. The same table
    // as lipsync.js's K.
    private object K {
        const val lmA = 300.0; const val lmB = 700.0; const val lmC = 800.0; const val lmD = 1400.0
        const val lmAdapt = 0.9; const val lmPrior = 4.0
        const val fbA = 1400.0; const val fbB = 2100.0; const val fbC = 2100.0; const val fbD = 3300.0
        const val fbAdapt = 0.8; const val fbPrior = 2.0; const val fbN0 = 80.0
        const val fricLo = 10.0; const val fricHi = 22.0; const val nasLo = 2.0; const val nasHi = 8.0
        const val shA = 300.0; const val shB = 1500.0; const val shC = 2500.0; const val shD = 5000.0
        const val shLo = 15.0; const val shHi = 25.0
        const val openRange = 30.0; const val lmOpen = 8.0; const val openMs = 25.0
        const val dipLo = 7.5; const val dipHi = 12.0; const val dipMix = 0.3
        const val wide0 = 7.0; const val wide1 = 7.0; const val round0 = 1.0; const val round1 = 3.5
        const val round2 = 6.0; const val lipFwdMs = 40.0; const val lipBackMs = 60.0; const val teeth = 0.45
        // A steady noise floor (see the gate in analyse): the quietest noiseQ
        // of the frames, +noiseAbove dB, never closer than noiseCap dB under
        // the peaks.
        const val noiseQ = 0.02; const val noiseAbove = 7.0; const val noiseCap = 18.0
        // The speaker's size (see pitchOf): the lip bands move by pitchAlpha x
        // the voice's pitch in quarter octaves from pitchRef Hz, within
        // pitchLo..pitchHi quarter octaves; a clip needs pitchN pitched frames.
        const val pitchRef = 210.0; const val pitchAlpha = 0.6; const val pitchLo = -1.5
        const val pitchHi = 0.0; const val pitchN = 5
    }

    /**
     * The median pitch (Hz) of the vowel frames (`vow > 0.5`), or 0 when
     * fewer than [K.pitchN] of them have a clear one. Every third vowel frame,
     * a normalised autocorrelation of the clip averaged down to about 6 kHz,
     * 32 ms long, over pitches of 70-400 Hz; the shortest period whose peak is
     * within 85 % of the best one (so not twice the period), refined between
     * samples by a parabola. As lipsync.js's `pitchOf`, operation for
     * operation, so the two give the same doubles.
     */
    private fun pitchOf(samples: FloatArray, sr: Int, vow: DoubleArray, n: Int): Double {
        if (sr < 4000) return 0.0 // below any rate Wav.rateOf accepts: no pitch, no move
        val dec =max(1, floor(sr / 6000.0 + 0.5).toInt())
        val r = sr.toDouble() / dec
        val len = samples.size / dec
        val y = DoubleArray(len)
        for (k in 0 until len) {
            var a = 0.0
            for (t in 0 until dec) a += samples[k * dec + t].toDouble()
            y[k] = a / dec
        }
        val w = floor(0.032 * r + 0.5).toInt()
        val l0 = floor(r / 400).toInt()
        val l1 = ceil(r / 70).toInt()
        val rr = DoubleArray(l1 + 2)
        val got = DoubleArray(n)
        var m = 0
        var c = 0
        for (i in 0 until n) {
            if (!(vow[i] > 0.5) || (c++ % 3) != 0) continue
            val st = floor(i.toDouble() * sr / FPS / dec).toInt() - (w shr 1)
            if (st < 0 || st + w + l1 + 1 > len) continue
            var e0 = 0.0
            var best = -1.0
            for (t in 0 until w) e0 += y[st + t] * y[st + t]
            for (l in l0 - 1..l1 + 1) {
                var xy = 0.0
                var ee = 0.0
                for (t in 0 until w) {
                    val v = y[st + t + l]; xy += y[st + t] * v; ee += v * v
                }
                rr[l] = xy / sqrt(e0 * ee + 1e-20)
            }
            for (l in l0..l1) if (rr[l] > best) best = rr[l]
            if (best < 0.6) continue
            for (l in l0..l1) {
                if (rr[l] >= 0.85 * best && rr[l] >= rr[l - 1] && rr[l] >= rr[l + 1]) {
                    val d2 = rr[l - 1] - 2 * rr[l] + rr[l + 1]
                    got[m++] = r / (l + (if (d2 < 0) 0.5 * (rr[l - 1] - rr[l + 1]) / d2 else 0.0))
                    break
                }
            }
        }
        return if (m >= K.pitchN) percentile(got, m, 0.5) else 0.0
    }

    /** [samples] in -1..1, mono. */
    fun analyse(samples: FloatArray, sampleRate: Int): Track {
        // A sample that is not a number (NaN, Infinity) would make every frame
        // near it NaN, and a NaN mouth reaches the face. It counts as silence
        // (as lipsync.js). The ShortArray path never has one.
        val finite = if (samples.all { it.isFinite() }) samples else FloatArray(samples.size) {
            if (samples[it].isFinite()) samples[it] else 0f
        }
        val src = if (sampleRate > 0) finite else FloatArray(0)
        val f = features(src, sampleRate)
        val n = f.n
        val b = f.bands
        val level = FloatArray(n)
        val open = FloatArray(n)
        val wide = FloatArray(n)
        val round = FloatArray(n)
        val tr = Track(FPS, level, open, wide, round)
        if (n == 0) return tr
        val tmp = DoubleArray(n)
        var m = 0
        for (i in 0 until n) if (f.all[i] > -80) tmp[m++] = f.all[i]
        if (m == 0) return tr
        // Loudness reference (robust peak) and the gate below which is silence.
        val ref = percentile(tmp, m, 0.95)
        val floorDb = percentile(tmp, m, 0.10)
        // A steady noise floor (a custom voice cloned from a noisy recording,
        // hiss, hum) fills the pauses at one level, which the 30 dB gate can
        // sit under: the gate goes 7 dB above the quietest 2 % of the frames,
        // never closer than 18 dB under the peaks. As lipsync.js.
        val gate = min(ref - K.noiseCap, max(min(ref - 30, max(ref - 50, floorDb + 8)),
            percentile(tmp, m, K.noiseQ) + K.noiseAbove))

        // ---- level: loudness 0..1, fast attack, slower release -------------
        val att = coef(20.0)
        val rel = coef(75.0)
        var env = 0.0
        for (i in 0 until n) {
            val x = clamp01((f.all[i] - gate) / (ref - gate))
            env += (x - env) * (if (x > env) att else rel)
            level[i] = env.toFloat()
        }

        // ---- per-frame acoustic cues (see lipsync.js for what each means) ---
        val dO = DoubleArray(n)
        val dH = DoubleArray(n)
        val dL = DoubleArray(n)
        val lm = DoubleArray(n)
        val fb = DoubleArray(n)
        // sh: 2.5-5 kHz vs 300-1500 Hz - the hiss of "sh", "ch" and a breath,
        // which sits inside the oral band where dH cannot see it.
        val sh = DoubleArray(n)
        val x80 = bandPos(80.0)
        val x300 = bandPos(300.0)
        val x1000 = bandPos(1000.0)
        val x4000 = bandPos(4000.0)
        val x10k = bandPos(10000.0)
        val xS0 = bandPos(K.shA)
        val xS1 = bandPos(K.shB)
        val xS2 = bandPos(K.shC)
        val xS3 = bandPos(K.shD)
        for (i in 0 until n) {
            val o = i * NB
            dO[i] = db(bandSum(b, o, x300, x4000))
            dH[i] = db(bandSum(b, o, x4000, x10k))
            dL[i] = db(bandSum(b, o, x80, x1000))
            sh[i] = db(bandSum(b, o, xS2, xS3)) - db(bandSum(b, o, xS0, xS1))
        }
        // (lm and fb are worked out further down, once the voice's size is known.)
        m = 0
        for (i in 0 until n) if (f.all[i] > gate) tmp[m++] = dO[i]
        val refO = percentile(tmp, m, 0.95)

        // Soft frame classes (0..1): hiss (s, sh, f, a breath), nasal/closed-lip murmur, vowel.
        val fric = DoubleArray(n)
        val nas = DoubleArray(n)
        val vow = DoubleArray(n)
        val speech = BooleanArray(n)
        val lo = DoubleArray(n)
        for (i in 0 until n) {
            speech[i] = f.all[i] > gate
            lo[i] = dL[i] - dO[i]
        }
        for (i in 0 until n) {
            fric[i] = if (speech[i]) {
                max(smooth01(K.fricLo, K.fricHi, dH[i] - dO[i]), smooth01(K.shLo, K.shHi, sh[i]))
            } else 0.0
            nas[i] = if (speech[i]) smooth01(K.nasLo, K.nasHi, lo[i]) else 0.0
            vow[i] = smooth01(refO - 22, refO - 10, dO[i]) * (1 - fric[i]) * (1 - nas[i])
        }

        // The voice's size: the lip bands move down with the voice's pitch - a
        // deeper voice (a man's, or any voice pitched down) has every
        // resonance lower, and its "ee" read round. By 0.6 of how far the
        // pitch is below 210 Hz, at most 3/8 of an octave, never up.
        // lipsync.js says why pitch and not the spectrum, and why not up.
        val f0 = pitchOf(src, sampleRate, vow, n)
        val size = if (f0 > 0) {
            max(K.pitchLo, min(K.pitchHi, K.pitchAlpha * 4 * ln(f0 / K.pitchRef) / LN2))
        } else 0.0
        val xE = bandPos(K.lmA) + size
        val xF = bandPos(K.lmB) + size
        val xG = bandPos(K.lmC) + size
        val xH = bandPos(K.lmD) + size
        val xA = bandPos(K.fbA) + size
        val xB = bandPos(K.fbB) + size
        val xC = bandPos(K.fbC) + size
        val xD = bandPos(K.fbD) + size
        for (i in 0 until n) {
            val o = i * NB
            lm[i] = db(bandSum(b, o, xE, xF)) - db(bandSum(b, o, xG, xH))
            fb[i] = db(bandSum(b, o, xC, xD)) - db(bandSum(b, o, xA, xB))
        }

        // The voice's own colour, centred on this clip's median vowel - in
        // proportion to how many vowels there are, and not all the way.
        m = 0
        for (i in 0 until n) if (vow[i] > 0.5) tmp[m++] = fb[i]
        val fbOff = if (m > 0) K.fbAdapt * (percentile(tmp, m, 0.5) - K.fbPrior) * m / (m + K.fbN0) else 0.0
        m = 0
        for (i in 0 until n) if (vow[i] > 0.5) tmp[m++] = lm[i]
        val lmOff = if (m > 0) K.lmAdapt * (percentile(tmp, m, 0.5) - K.lmPrior) * m / (m + K.fbN0) else 0.0

        // ---- open ---------------------------------------------------------------
        val ot = DoubleArray(n)
        for (i in 0 until n) {
            if (!speech[i]) continue
            val u = clamp01((dO[i] - refO + K.openRange) / K.openRange)
            val jaw = clamp01((K.lmOpen - lm[i] + lmOff) / 12)
            ot[i] = u.pow(1.4) * (0.55 + 0.45 * jaw) * (1 - 0.8 * nas[i]) * (1 - 0.6 * fric[i])
        }
        smoothFB(ot, coef(K.openMs), coef(K.openMs))

        // Short dips in the oral energy between two louder stretches: m, b, p
        // (and t, d, n). The mouth closes for the dip.
        val cl = DoubleArray(n)
        for (i in 1 until n - 1) {
            if (!(dO[i] <= dO[i - 1] && dO[i] < dO[i + 1])) continue
            var lMax = -1e9
            var rMax = -1e9
            for (j in max(0, i - 12)..i) if (dO[j] > lMax) lMax = dO[j]
            for (j in i..min(n - 1, i + 12)) if (dO[j] > rMax) rMax = dO[j]
            if (lMax < refO - 15 || rMax < refO - 15) continue
            val depth = min(lMax, rMax) + K.dipMix * (max(lMax, rMax) - min(lMax, rMax)) - dO[i]
            val cs = smooth01(K.dipLo, K.dipHi, depth)
            if (cs <= 0) continue
            val lim = dO[i] + 0.5 * depth
            var a = i
            var bb = i
            while (a > 0 && dO[a - 1] < lim) a--
            while (bb < n - 1 && dO[bb + 1] < lim) bb++
            if (bb - a + 1 > 14) continue
            for (j in a..bb) if (cs > cl[j]) cl[j] = cs
        }
        // The same at the edge of a pause, where a dip has only one side.
        for (i in 0 until n) {
            if (!speech[i]) continue
            val edgeL = i == 0 || !speech[i - 1]
            val edgeR = i == n - 1 || !speech[i + 1]
            if (!edgeL && !edgeR) continue
            val dir = if (edgeL) 1 else -1
            var pk = -1e9
            var j = i
            while (j >= 0 && j < n && abs(j - i) <= 25) {
                if (dO[j] > pk) pk = dO[j]
                j += dir
            }
            if (pk < refO - 15) continue
            j = i
            while (j >= 0 && j < n && abs(j - i) < 15 && speech[j]) {
                val ce = smooth01(K.dipLo, K.dipHi, pk - dO[j]) * smooth01(-2.0, 2.0, lo[j])
                if (ce <= 0.05) break
                if (ce > cl[j]) cl[j] = ce
                j += dir
            }
        }
        smoothFB(cl, coef(8.0), coef(8.0))

        // Pauses: a silent stretch of 80 ms or more closes the mouth fully,
        // 40 ms into the silence; it starts opening 30 ms before speech resumes.
        val pm = DoubleArray(n) { 1.0 }
        var i0 = 0
        while (i0 < n) {
            if (speech[i0]) { i0++; continue }
            var j = i0
            while (j < n && !speech[j]) j++
            if (j - i0 >= 8) {
                for (k in i0 until j) {
                    val dl = if (i0 > 0) k - i0 + 1 else 99
                    val dr = if (j < n) j - k else 99
                    pm[k] = max(clamp01(1 - dl / 4.0), clamp01(1 - dr / 4.0))
                }
            }
            i0 = j
        }

        for (i in 0 until n) {
            val ov = ot[i] * (1 - cl[i]) * pm[i]
            open[i] = clamp01(1.15 * ov / (1 + 0.15 * ov)).toFloat()
        }

        // ---- wide / round -------------------------------------------------------
        val nw = DoubleArray(n)
        val nr = DoubleArray(n)
        val den = DoubleArray(n)
        val fr2 = DoubleArray(n)
        for (i in 0 until n) {
            val f2 = fb[i] - fbOff
            val wt = clamp01((f2 - K.wide0) / K.wide1)
            val rt = clamp01((lm[i] - lmOff - K.round0) / K.round1) * clamp01((K.round2 - f2) / K.wide1)
            nw[i] = vow[i] * wt; nr[i] = vow[i] * rt; den[i] = vow[i]; fr2[i] = fric[i]
        }
        val lf = coef(K.lipFwdMs)
        val lb = coef(K.lipBackMs)
        smoothFB(nw, lf, lb); smoothFB(nr, lf, lb); smoothFB(den, lf, lb); smoothFB(fr2, coef(20.0), coef(20.0))
        for (i in 0 until n) {
            val pres = clamp01(den[i] / 0.3) * pm[i]
            var wv = if (den[i] > 1e-6) nw[i] / den[i] else 0.0
            var rv = if (den[i] > 1e-6) nr[i] / den[i] else 0.0
            wv = max(wv * pres, K.teeth * fr2[i] * pm[i])
            rv *= pres
            wide[i] = clamp01(wv * (1 - rv)).toFloat()
            round[i] = clamp01(rv * (1 - wv)).toFloat()
        }
        return tr
    }
}
