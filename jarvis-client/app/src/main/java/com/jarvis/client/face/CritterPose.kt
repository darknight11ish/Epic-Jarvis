package com.jarvis.client.face

import com.jarvis.client.FaceState
import kotlin.math.PI
import kotlin.math.abs
import kotlin.math.cos
import kotlin.math.exp
import kotlin.math.floor
import kotlin.math.max
import kotlin.math.min
import kotlin.math.pow
import kotlin.math.sin
import kotlin.math.sqrt

/**
 * The red panda's body language: where its head, ears, eyes, paws, tail and
 * orb are on any frame, for any of Jarvis's eight states - and the helpers
 * every animal shares.
 *
 * A line-for-line copy of the desktop's `jarvis-desktop/src/critter-pose.js`.
 * The two cannot share code, so they share answers instead:
 * `tools/gen_critters.py` runs the JavaScript at fixed moments and saves what
 * it returns in `critter-pose-golden.json`, and `CritterPoseTest` fails if
 * this file disagrees. Change one, change the other, re-run the generator.
 *
 * The shader (`CritterShaders.RED_PANDA`, generated from the same source as
 * the desktop's) only draws a panda in the pose this hands it.
 *
 * Everything here is a pure function of its arguments - nothing carries over
 * from the last frame - so [RedPanda] stays pinnable like the other
 * deterministic faces. What looks random (glances, blinks, stretches) is a
 * hash of the clock, so both apps draw the same "random" panda.
 *
 * The motion follows published work, credited where it is used and in
 * THIRD-PARTY-NOTICES.txt: Daniel Holden's Spring-It-On (settling into a new
 * state), Mika Suominen's TalkingHead (hold-then-ease, blinks, eyes leading
 * the head), moeru-ai's airi (pauses between glances) and pixiv's ChatVRM
 * (how much of a look the head takes). All MIT.
 *
 * Coordinates: x to the viewer's right, y up, the panda faces -z.
 */
object CritterPose {

    /** About how long the BODY takes to settle into a new state, in seconds. */
    const val BLEND_S = 0.55f

    // Overlapping action: each part settles with its own half-life (the
    // desktop's HL_* - see its note).
    internal const val HL_EYES = 0.035f
    internal const val HL_MOUTH = 0.07f
    internal const val HL_HEAD = 0.13f
    internal const val HL_LIMB = 0.15f
    internal const val HL_BODY = 0.18f
    internal const val HL_TRAIL = 0.22f

    // The pose as a flat array so two can be blended element by element.
    // Same order as the desktop's KEYS.
    private const val HEAD_YAW = 0
    private const val HEAD_PITCH = 1
    private const val HEAD_ROLL = 2
    private const val LEAN = 3
    private const val BOB = 4
    private const val BREATH = 5
    private const val EAR_L = 6
    private const val EAR_R = 7
    private const val EYE_L = 8
    private const val EYE_R = 9
    private const val BROW = 10
    private const val SPEAK = 11
    private const val LOOK_X = 12
    private const val LOOK_Y = 13
    private const val PAW_LX = 14
    private const val PAW_LY = 15
    private const val PAW_LZ = 16
    private const val PAW_RX = 17
    private const val PAW_RY = 18
    private const val PAW_RZ = 19
    private const val TAIL_SWING = 20
    private const val TAIL_CURL = 21
    private const val ORB_X = 22
    private const val ORB_Y = 23
    private const val ORB_Z = 24
    private const val ORB_R = 25
    private const val ORB_GLOW = 26
    private const val BODY_ROLL = 27
    private const val EAR_TW_L = 28
    private const val EAR_TW_R = 29
    private const val TAIL_2 = 30
    private const val TAIL_3 = 31
    private const val TAIL_4 = 32
    private const val TAIL_5 = 33
    private const val ASLEEP = 34
    private const val N = 35

    private const val TAU = (2.0 * PI).toFloat()
    private const val PI_F = PI.toFloat()

    /** The pointer: -1..1 from the centre, y up, and how much to follow it. */
    data class Look(val x: Float = 0f, val y: Float = 0f, val w: Float = 0f)

    /**
     * A small integer hash, exact in both languages - see the desktop's own
     * note on why not `fract(sin(n) * 43758)`.
     */
    fun hash01(n: Int): Float {
        var x = n xor 0x5bd1e995
        x = (x xor (x ushr 15)) * 0x2c1b3c6d
        x = (x xor (x ushr 12)) * 0x297a2d39
        x = x xor (x ushr 15)
        return ((x.toLong() and 0xffffffffL).toDouble() / 4294967296.0).toFloat()
    }

    internal fun clamp(v: Float, lo: Float, hi: Float) = max(lo, min(hi, v))
    internal fun smooth(k: Float) = k * k * (3f - 2f * k)

    /**
     * An ease in and out that starts and ends at rest ("smootherstep") - the
     * desktop's ease(), in place of TalkingHead's sigmoidFactory(5), whose
     * ends were not quite still.
     */
    internal fun ease(x: Float): Float {
        val k = clamp(x, 0f, 1f)
        return k * k * k * (k * (6f * k - 15f) + 10f)
    }

    // --- the clock, kept small (the desktop's LOOP note) --------------------

    internal const val LOOP = 1024f
    internal fun loopT(t: Float) = t - LOOP * floor(t / LOOP)
    /** Everything that looks random repeats every PERIOD seconds - the desktop's note. */
    internal const val PERIOD = 4096
    /** Slot number [n] of [span]-second slots, taken round PERIOD. */
    private fun slotId(n: Int, span: Float): Int = n and ((PERIOD / span).toInt() - 1)
    /** A sine making exactly [k] cycles per LOOP (k / 1024 cycles a second). */
    internal fun wave(t: Float, k: Float, ph: Float): Float = sin(phaseOf(t, k) + ph)
    /** Where a rhythm of [k] cycles per LOOP is at clock [t]: 0..2pi. */
    internal fun phaseOf(t: Float, k: Float): Float {
        val u = (loopT(t) / LOOP) * k
        return TAU * (u - floor(u))
    }
    internal const val TAU_F = TAU
    /** 0 at both ends, 1 in the middle, easing in and out (x in 0..1). */
    internal fun bump(x: Float): Float {
        if (x <= 0f || x >= 1f) return 0f
        val s = sin(PI_F * x)
        return s * s
    }
    /** Eases up over [a] seconds, holds for [h], eases down over [r]; 0 outside. */
    internal fun envAHR(x: Float, a: Float, h: Float, r: Float): Float {
        if (x <= 0f || x >= a + h + r) return 0f
        if (x < a) return smooth(x / a)
        if (x < a + h) return 1f
        return smooth(1f - (x - a - h) / r)
    }

    // --- things that happen now and then (the desktop's notes) -------------

    /** TalkingHead's gaussianRandom (MIT), with the hash in place of Math.random. */
    internal fun gauss(id: Int, salt: Int, lo: Float, hi: Float, skew: Float): Float {
        var r = 0f
        for (i in 0 until 5) r += hash01(id * 256 + salt + i)
        return lo + (r / 5f).pow(skew) * (hi - lo)
    }

    /** The pause before the eyes' next dart: moeru-ai/airi's randomSaccadeInterval table (MIT). */
    private val SACCADE_P = floatArrayOf(0.075f, 0.185f, 0.31f, 0.45f, 0.575f, 0.625f, 0.665f, 0.695f, 0.715f, 1.0f)
    internal fun saccadeGap(id: Int, salt: Int): Float {
        val r = hash01(id * 256 + salt)
        var i = 0
        while (i < 9 && r > SACCADE_P[i]) i++
        return 0.8f + 0.4f * i + 0.4f * hash01(id * 256 + salt + 1)
    }

    private class Hit(val k: Int, val at: Float)
    private fun lastIn(n: Int, span: Float, limit: Float, salt: Int, lo: Float, hi: Float, skew: Float): Hit {
        var k = -1
        var at = 0f
        for (j in 0 until 32) {
            val next = at + gauss(slotId(n, span) * 32 + j, salt, lo, hi, skew)
            if (next > limit || next >= span) break
            k = j; at = next
        }
        return Hit(k, at)
    }

    /** The desktop's chain(): [id], seconds [since] it, the one before ([prev]), seconds [until] the next, [hold] between the two. */
    internal class Chain(val id: Int, val since: Float, val prev: Int, val until: Float, val hold: Float)
    internal fun chain(t: Float, span: Float, salt: Int, lo: Float, hi: Float, skew: Float): Chain {
        val n = floor(t / span).toInt()
        val local = t - n * span
        var a = lastIn(n, span, local, salt, lo, hi, skew)
        var cn = n
        var cLocal = local
        if (a.k < 0) { cn = n - 1; cLocal = local + span; a = lastIn(cn, span, span, salt, lo, hi, skew) }
        val id = slotId(cn, span) * 32 + a.k
        val since = cLocal - a.at
        val nx = a.at + gauss(id + 1, salt, lo, hi, skew)
        val until = if (nx < span) nx - cLocal else span + gauss(slotId(cn + 1, span) * 32, salt, lo, hi, skew) - cLocal
        val prev: Int
        val hold: Float
        if (a.k > 0) {
            prev = id - 1
            hold = gauss(id, salt, lo, hi, skew)
        } else {
            val b = lastIn(cn - 1, span, span, salt, lo, hi, skew)
            prev = slotId(cn - 1, span) * 32 + b.k
            hold = span - b.at + a.at
        }
        return Chain(id, since, prev, until, hold)
    }

    /** 0 open .. 1 shut: TalkingHead's blink (MIT) - see the desktop's blinkAt. */
    internal fun blinkAt(t: Float, salt: Int, slow: Float, lo: Float, hi: Float): Float {
        val c = chain(t, 32f, salt, lo, hi, 1.6f)
        val shut = (0.06f + 0.1f * hash01(c.id * 256 + salt + 5)) * slow
        fun lid(x: Float): Float {
            if (x <= 0f) return 0f
            if (x < 0.06f * slow) return smooth(x / (0.06f * slow))
            if (x < 0.06f * slow + shut) return 1f
            return 1f - smooth(clamp((x - 0.06f * slow - shut) / (0.10f * slow), 0f, 1f))
        }
        val one = lid(c.since)
        val two = if (hash01(c.id * 256 + salt + 6) < 0.15f) lid(c.since - (0.06f * slow + shut + 0.10f * slow + 0.12f)) else 0f
        return max(one, two)
    }
    /** The panda's blinks, 0 open .. 1 shut. */
    fun blink(t: Float): Float = blinkAt(t, S_BLINK, 1f, 2f, 10f)

    private val NONE = floatArrayOf(-1f, 0f, 0f)
    private const val RUN_MAX = 32
    private fun pickKind(r: Float, kinds: FloatArray, avoid: Int): Int {
        var total = 0f
        for (i in kinds.indices) if (i != avoid) total += kinds[i]
        var x = r * total
        for (i in kinds.indices) {
            if (i == avoid) continue
            if (x < kinds[i]) return i
            x -= kinds[i]
        }
        for (i in kinds.indices.reversed()) if (i != avoid) return i
        return 0
    }
    private fun kindAt(n: Int, slot: Float, salt: Int, chance: Float, kinds: FloatArray): Int {
        fun has(m: Int) = hash01(slotId(m, slot) * 256 + salt) < chance
        if (!has(n)) return -1
        if (kinds.size < 2) return 0
        var m = n
        while (m > n - RUN_MAX && has(m - 1)) m--
        var k = -1
        for (j in m..n) k = pickKind(hash01(slotId(j, slot) * 256 + salt + 1), kinds, k)
        return k
    }
    private val EVEN = Array(6) { i -> FloatArray(i + 1) { 1f } }
    /**
     * The desktop's happening(): [kind (or -1), seconds since it started, the
     * clock it starts at]. [kinds] is how often each kind comes up; never the
     * same kind as the slot before.
     */
    internal fun happening(t: Float, slot: Float, lead: Float, spread: Float, salt: Int, chance: Float, kinds: FloatArray): FloatArray {
        val n = floor(t / slot).toInt()
        val kind = kindAt(n, slot, salt, chance, kinds)
        if (kind < 0) return NONE
        val off = lead + spread * hash01(slotId(n, slot) * 256 + salt + 2)
        // (t - n * slot) first: exact on a 32-bit clock, days long.
        return floatArrayOf(kind.toFloat(), t - n * slot - off, n * slot + off)
    }
    /** [count] kinds, all as often. */
    internal fun happening(t: Float, slot: Float, lead: Float, spread: Float, salt: Int, chance: Float, count: Int): FloatArray =
        happening(t, slot, lead, spread, salt, chance, EVEN[count - 1])

    /**
     * A talking gesture, in phrases, never the same kind twice running and
     * never within [LOOK_CLEAR] of a look that moves the eyes - the desktop's
     * beat().
     */
    private val BEAT_KINDS = floatArrayOf(4f, 3f, 3f)
    internal const val LOOK_CLEAR = 1.5f
    internal fun beat(t: Float, salt: Int, gazeSalt: Int, lo: Float, hi: Float, contact: Float): FloatArray {
        val b = happening(t, 2f, 0f, 0.6f, salt, 0.45f, BEAT_KINDS)
        if (b[0] < 0f) return b
        fun atYou(id: Int) = hash01(id * 256 + gazeSalt + 5) < contact
        fun moves(c: Chain) = !(atYou(c.id) && atYou(c.prev))
        val c = chain(b[2], 32f, gazeSalt, lo, hi, 1.3f)
        if (c.since < LOOK_CLEAR && moves(c)) return NONE
        val n = chain(b[2] + LOOK_CLEAR, 32f, gazeSalt, lo, hi, 1.3f)
        if (n.id != c.id && moves(n)) return NONE
        return b
    }

    /** A slow weight shift, -1..1: TalkingHead's hold-then-ease (MIT), eased by [ease]. */
    internal fun shift(t: Float, salt: Int): Float {
        val c = chain(t, 32f, salt, 3f, 9f, 1f)
        val a = 2f * hash01(c.prev * 256 + salt + 5) - 1f
        val b = 2f * hash01(c.id * 256 + salt + 5) - 1f
        return a + (b - a) * ease(c.since / 2.0f)
    }

    // Where it is looking: TalkingHead's looks, ChatVRM's head share, airi's darts.
    private fun lookX(id: Int, salt: Int, contact: Float, sx: Float): Float =
        if (hash01(id * 256 + salt + 5) < contact) 0f else sx * (2f * hash01(id * 256 + salt + 6) - 1f)
    private fun lookY(id: Int, salt: Int, contact: Float, sy: Float, yb: Float): Float =
        if (hash01(id * 256 + salt + 5) < contact) 0f else yb + sy * (2f * hash01(id * 256 + salt + 7) - 1f)
    private fun dartAt(id: Int, since: Float, hold: Float, salt: Int, amp: Float): FloatArray {
        var at = 0f
        var x = 0f
        var y = 0f
        var age = since
        for (j in 0 until 8) {
            val next = at + saccadeGap(id * 8 + j, salt + 8)
            if (next > since || next > hold - 0.6f) break
            at = next
            x = amp * (2f * hash01((id * 8 + j) * 256 + salt + 10) - 1f)
            y = 0.6f * amp * (2f * hash01((id * 8 + j) * 256 + salt + 11) - 1f)
            age = since - at
        }
        return floatArrayOf(x, y, age)
    }
    /** [eyes x, eyes y, head x, head y, blink] - the desktop's gaze(). */
    internal fun gaze(
        t: Float, salt: Int, lo: Float, hi: Float, contact: Float,
        sx: Float, sy: Float, yb: Float, dart: Float, headS: Float,
    ): FloatArray {
        val c = chain(t, 32f, salt, lo, hi, 1.3f)
        val x1 = lookX(c.id, salt, contact, sx)
        val y1 = lookY(c.id, salt, contact, sy, yb)
        val x0 = lookX(c.prev, salt, contact, sx)
        val y0 = lookY(c.prev, salt, contact, sy, yb)
        val d0 = dartAt(c.prev, c.hold, c.hold, salt, dart)
        val d1 = dartAt(c.id, c.since, c.since + c.until, salt, dart)
        val e = smooth(clamp(c.since / 0.07f, 0f, 1f))
        val de = smooth(clamp(d1[2] / 0.05f, 0f, 1f))
        val fx = x0 + d0[0]
        val fy = y0 + d0[1]
        val ex = fx + (x1 - fx) * e + d1[0] * de
        val ey = fy + (y1 - fy) * e + d1[1] * de
        val h = ease((c.since - 0.12f) / headS)
        val big = if (abs(x1 - x0) > 0.9f) bump(c.since / 0.2f) else 0f
        return floatArrayOf(ex, ey, x0 + (x1 - x0) * h, y0 + (y1 - y0) * h, big)
    }

    /**
     * The three ways of asking an animal to move less - the desktop's
     * optsOf(). Each is a weight, 0 (off) to 1 (on), which the host eases
     * over about a second when it is switched so nothing snaps.
     *
     * @param calm the owner's calm motion: smaller head turns and rhythmic
     *   movements, no idle happenings or talking gestures.
     * @param serious a crisis moment ("calm and plain"): a calm, attentive
     *   listener - no happenings, gestures, playful poses or tilts; slower,
     *   steadier looks.
     * @param still the owner's "Still" option: it only breathes and blinks,
     *   its eyes resting on you.
     */
    data class Opts(val calm: Float = 0f, val serious: Float = 0f, val still: Float = 0f) {
        internal fun norm() = Opts(clamp(calm, 0f, 1f), clamp(serious, 0f, 1f), clamp(still, 0f, 1f))
        /** How much of the idle happenings and talking gestures is left. */
        internal val hap: Float get() = 1f - max(calm, max(serious, still))
        /** The head's share of a look. */
        internal val head: Float get() = (1f - 0.6f * max(calm, serious)) * (1f - still)
        /** How much of the slow rhythmic movements is left. */
        internal val sway: Float get() = (1f - 0.5f * calm) * (1f - 0.7f * serious) * (1f - still)
        /** How much of a playful or tilted pose is left. */
        internal val play: Float get() = 1f - serious
    }

    private fun mix5(a: FloatArray, b: FloatArray, k: Float): FloatArray =
        FloatArray(5) { i -> a[i] + (b[i] - a[i]) * k }
    /** Eyes on you, with only tiny darts - the desktop's restingGaze(). */
    internal fun restingGaze(t: Float, salt: Int): FloatArray = gaze(t, salt, 2f, 7f, 1f, 0f, 0f, 0f, 0.03f, 1.1f)
    /** [gaze] with the options folded in - the desktop's looks(). */
    internal fun looks(
        t: Float, salt: Int, lo: Float, hi: Float, contact: Float,
        sx: Float, sy: Float, yb: Float, dart: Float, headS: Float, o: Opts,
    ): FloatArray {
        var g = gaze(t, salt, lo, hi, contact, sx, sy, yb, dart, headS)
        if (o.serious > 0f) {
            g = mix5(g, gaze(t, salt, 3f, 9f, max(contact, 0.6f), 0.6f * sx, 0.6f * sy, yb, 0.5f * dart, 1.5f * headS), o.serious)
        }
        if (o.still > 0f) g = mix5(g, restingGaze(t, salt), o.still)
        val k = o.head
        return floatArrayOf(g[0], g[1], k * g[2], k * g[3], g[4])
    }

    // The panda's own dice.
    private const val S_GAZE = 0
    private const val S_EVENT = 16
    private const val S_ROLL = 24
    private const val S_LEAN = 32
    private const val S_BEAT = 40
    private const val S_BLINK = 48

    // Its idle happenings, and how often each comes up (the desktop's EVENTS):
    // stretch, tail flick, scratch, hears left, hears right.
    private val EVENTS = floatArrayOf(12f, 30f, 12f, 23f, 23f)

    /** The tail's swing at clock [t] in one state; the tip is asked for an earlier time. */
    private fun tailAt(state: FaceState, t: Float, o: Opts): Float {
        val sw = o.sway
        return when (state) {
            FaceState.LISTENING -> sw * 0.12f * wave(t, 123f, 0f)
            FaceState.THINKING -> sw * 0.2f * wave(t, 205f, 0f)
            FaceState.SPEAKING -> sw * 0.14f * wave(t, 111f, 1.0f)
            FaceState.APPROVAL -> sw * 0.04f * wave(t, 81f, 0f)
            FaceState.STANDBY -> 0f
            FaceState.ERROR -> sw * 0.03f * wave(t, 81f, 0f)
            FaceState.BANKED -> sw * 0.03f * wave(t, 70f, 0f)
            FaceState.IDLE -> {
                var s = sw * (0.16f * wave(t, 87f, 0f) + 0.08f * wave(t, 139f, 1.7f) - 0.065f * shift(t - 0.6f, S_ROLL))
                val ev = happening(t, 16f, 0.5f, 5.5f, S_EVENT, 0.7f, EVENTS)
                if (ev[0] == 1f) s += o.hap * 0.32f * (bump(ev[1] / 0.8f) - 0.3f * bump((ev[1] - 0.6f) / 0.9f))
                s
            }
        }
    }
    private const val TAIL_LAG = 0.12f

    // Where things rest, in the body's own frame (origin on the seat).
    private val LAP_ORB = floatArrayOf(0f, 0.34f, -0.44f, 0.095f)
    private val LAP_PAW_L = floatArrayOf(-0.15f, 0.30f, -0.40f)
    private val LAP_PAW_R = floatArrayOf(0.15f, 0.30f, -0.40f)

    // The neck in the body's frame, and how much bigger the head is drawn.
    private val NECK = floatArrayOf(0f, 0.60f, -0.02f)
    private const val HEAD_S = 1.14f
    private fun headTurn(p: FloatArray): FloatArray = mul(ry(-p[HEAD_YAW]), mul(rx(p[HEAD_PITCH]), rz(-p[HEAD_ROLL])))
    /** A point in the head's own (unscaled) frame, in the body's frame. */
    private fun onHead(p: FloatArray, x: Float, y: Float, z: Float): FloatArray {
        val v = apply(headTurn(p), x * HEAD_S, y * HEAD_S, z * HEAD_S)
        return floatArrayOf(NECK[0] + v[0], NECK[1] + v[1], NECK[2] + v[2])
    }

    /** The pose for ONE state at clock [t]. See the desktop's stateTargets; [o] as [Opts]. */
    fun stateTargets(state: FaceState, t: Float, amp: Float, look: Look, since: Float = 1e9f, o: Opts = Opts()): FloatArray {
        val hap = o.hap
        val sw = o.sway
        val play = o.play
        val p = FloatArray(N)
        p[HEAD_YAW] = 0f; p[HEAD_PITCH] = 0f; p[HEAD_ROLL] = 0f; p[LEAN] = 0f; p[BOB] = 0f; p[BREATH] = 1f
        p[EAR_L] = 0.2f; p[EAR_R] = 0.2f; p[EYE_L] = 1f; p[EYE_R] = 1f; p[BROW] = 0f; p[SPEAK] = 0f
        p[LOOK_X] = 0f; p[LOOK_Y] = 0f
        p[PAW_LX] = LAP_PAW_L[0]; p[PAW_LY] = LAP_PAW_L[1]; p[PAW_LZ] = LAP_PAW_L[2]
        p[PAW_RX] = LAP_PAW_R[0]; p[PAW_RY] = LAP_PAW_R[1]; p[PAW_RZ] = LAP_PAW_R[2]
        p[TAIL_SWING] = 0f; p[TAIL_CURL] = 0.75f
        p[ORB_X] = LAP_ORB[0]; p[ORB_Y] = LAP_ORB[1]; p[ORB_Z] = LAP_ORB[2]; p[ORB_R] = LAP_ORB[3]
        p[ORB_GLOW] = 0.55f
        p[ASLEEP] = if (state == FaceState.STANDBY) 1f else 0f
        // 256 cycles a loop is one breath every 4 seconds.
        var breathK = 256f
        var breathDepth = 1f
        var blinkSlow = 1f
        var blinks = true
        var turnBlink = 0f
        var eyeK = 1f
        var deepBreath = 0f
        var scratch = 0f
        var lift = 0f

        when (state) {
            FaceState.LISTENING -> {
                val g = looks(t, S_GAZE, 2f, 7f, 0.8f, 0.2f, 0.1f, 0f, 0.05f, 1.1f, o)
                p[HEAD_ROLL] = play * 0.26f + sw * 0.025f * wave(t, 205f, 0f)
                p[HEAD_PITCH] = 0.06f
                p[HEAD_YAW] = 0.1f * g[2]
                p[LEAN] = 0.10f
                p[EAR_L] = 1f + 0.12f * amp + sw * 0.04f * wave(t, 170f, 0f)
                p[EAR_R] = 1f + 0.12f * amp + sw * 0.04f * wave(t, 170f, 1.9f)
                p[EYE_L] = 1f + 0.12f * play; p[EYE_R] = p[EYE_L]
                p[BROW] = 0.3f + 0.4f * play
                p[LOOK_X] = g[0] - 0.4f * g[2]; p[LOOK_Y] = 0.1f + g[1] - 0.4f * g[3]
                p[ORB_GLOW] = 0.55f + 0.5f * amp
                turnBlink = g[4]
            }
            FaceState.THINKING -> {
                val bob = sw * 0.02f * wave(t, 359f, 0f)
                val g = looks(t, S_GAZE, 1.8f, 6f, 0.55f, 0.7f, 0.2f, 0.75f, 0.05f, 1.1f, o)
                p[ORB_X] = 0f; p[ORB_Y] = 0.58f + bob; p[ORB_Z] = -0.56f; p[ORB_R] = 0.125f
                p[PAW_LX] = -0.12f; p[PAW_LY] = 0.50f + bob; p[PAW_LZ] = -0.52f
                p[PAW_RX] = 0.12f; p[PAW_RY] = 0.50f + bob; p[PAW_RZ] = -0.52f
                p[HEAD_PITCH] = -0.34f + sw * 0.03f * wave(t, 147f, 0f) + 0.22f * g[3]
                p[HEAD_YAW] = 0.15f * g[2]
                p[HEAD_ROLL] = sw * 0.08f * wave(t, 98f, 0f)
                p[LOOK_X] = g[0] - 0.4f * g[2]
                p[LOOK_Y] = -0.7f + g[1] - 0.4f * g[3]
                p[EAR_L] = 0.05f; p[EAR_R] = 0.05f
                p[BROW] = 0.25f
                p[LEAN] = 0.06f
                p[ORB_GLOW] = 0.95f + 0.2f * wave(t, 424f, 0f)
                turnBlink = g[4]
            }
            FaceState.SPEAKING -> {
                // Phrase-sized gestures, never on top of a look (see [beat]); the
                // eyes lead each look and the head follows only a little. The mouth
                // follows the words being heard (see [mouthOf]); `speak` only says
                // how much of it to show.
                val g = looks(t, S_GAZE, 1.8f, 6f, 0.65f, 0.5f, 0.18f, 0f, 0.06f, 1.1f, o)
                val b = beat(t, S_BEAT, S_GAZE, 1.8f, 6f, 0.65f)
                val x = b[1]
                p[SPEAK] = 1f
                p[LEAN] = 0.05f
                p[HEAD_PITCH] = 0.03f
                p[HEAD_YAW] = sw * 0.05f * wave(t, 111f, 0f) + 0.08f * g[2]
                p[HEAD_ROLL] = sw * 0.035f * wave(t, 93f, 0.5f)
                p[LOOK_X] = g[0] - 0.16f * g[2]; p[LOOK_Y] = g[1] - 0.16f * g[3]
                p[BROW] = 0.3f + 0.1f * amp
                p[EAR_L] = 0.45f; p[EAR_R] = 0.45f
                p[ORB_GLOW] = 0.6f + 0.45f * amp
                if (b[0] == 0f) {
                    p[HEAD_PITCH] -= hap * 0.06f * (bump(x / 0.7f) - 0.3f * bump((x - 0.55f) / 0.7f))
                    p[BROW] += hap * 0.25f * bump(x / 0.7f)
                } else if (b[0] == 1f) {
                    val e = hap * envAHR(x, 0.4f, 0.3f, 0.6f)
                    p[PAW_RX] += 0.10f * e; p[PAW_RY] += 0.16f * e; p[PAW_RZ] -= 0.06f * e
                    p[HEAD_PITCH] -= hap * 0.025f * bump(x / 0.9f)
                } else if (b[0] == 2f) {
                    p[HEAD_ROLL] += hap * play * 0.06f * bump(x / 1.2f)
                    p[BROW] += hap * 0.15f * bump(x / 1.2f)
                }
                turnBlink = g[4]
            }
            FaceState.APPROVAL -> {
                // Waiting on you, perhaps on something serious: sits up, leans in,
                // still and attentive, no wave - only its eyes' tiny darts move.
                val g = restingGaze(t, S_GAZE)
                p[LEAN] = 0.10f
                p[HEAD_PITCH] = 0.04f
                p[EYE_L] = 1f + 0.12f * play; p[EYE_R] = p[EYE_L]
                p[BROW] = 0.45f
                p[EAR_L] = 1.0f; p[EAR_R] = 1.0f
                p[TAIL_CURL] = 0.8f
                p[PAW_LY] += 0.10f; p[PAW_RY] += 0.10f; p[ORB_Y] += 0.10f
                p[LOOK_X] = g[0]; p[LOOK_Y] = g[1]
                p[ORB_GLOW] = 0.9f
                lift = 0.015f; blinkSlow = 1.4f
            }
            FaceState.STANDBY -> {
                val e = happening(t, 16f, 0.5f, 5.5f, S_EVENT, 0.35f, 1)
                val sigh = if (e[0] == 0f) bump(e[1] / 4.5f) else 0f
                p[EYE_L] = 0f; p[EYE_R] = 0f
                p[HEAD_PITCH] = -0.40f - 0.035f * sigh
                p[HEAD_ROLL] = 0.22f * play
                p[LEAN] = 0.06f
                p[EAR_L] = -0.7f; p[EAR_R] = -0.7f
                p[TAIL_CURL] = 1f
                p[ORB_GLOW] = 0.15f
                deepBreath = sigh
                // 171 cycles a loop: a breath every 6 seconds.
                breathK = 171f; breathDepth = 1.8f; blinks = false
            }
            FaceState.ERROR -> {
                // A still, concerned look; nothing comic. Only the eyes' tiny darts.
                val g = restingGaze(t, S_GAZE)
                p[HEAD_ROLL] = -0.12f * play
                p[HEAD_PITCH] = -0.08f
                p[EAR_L] = -0.15f; p[EAR_R] = -0.15f
                p[EYE_L] = 0.8f; p[EYE_R] = 0.8f
                p[BROW] = -0.25f
                p[LOOK_X] = g[0]; p[LOOK_Y] = -0.3f + g[1]
                p[ORB_GLOW] = 0.35f
                blinkSlow = 1.4f
            }
            FaceState.BANKED -> {
                val e = happening(t, 16f, 0.5f, 5.5f, S_EVENT, 0.55f, 1)
                val x = e[1]
                val droop = if (e[0] == 0f) {
                    if (x < 3.2f) smooth(clamp(x / 3.2f, 0f, 1f)) else 1f - smooth(clamp((x - 3.2f) / 0.8f, 0f, 1f))
                } else 0f
                p[EYE_L] = 0.35f * (1f - 0.7f * droop); p[EYE_R] = p[EYE_L]
                p[HEAD_PITCH] = -0.15f - 0.12f * droop
                p[EAR_L] = -0.2f - 0.2f * droop; p[EAR_R] = p[EAR_L]
                p[LOOK_Y] = -0.2f
                p[ORB_GLOW] = 0.25f
                p[TAIL_CURL] = 0.9f
                // 205 cycles a loop: a breath every 5 seconds.
                breathK = 205f; blinkSlow = 2.5f
            }
            FaceState.IDLE -> {
                val g = looks(t, S_GAZE, 1.5f, 6f, 0.35f, 0.8f, 0.25f, 0f, 0.08f, 1.1f, o)
                val gLag = looks(t - 0.3f, S_GAZE, 1.5f, 6f, 0.35f, 0.8f, 0.25f, 0f, 0.08f, 1.1f, o)
                val ev = happening(t, 16f, 0.5f, 5.5f, S_EVENT, 0.7f, EVENTS)
                val x = ev[1]
                val roll = sw * 0.025f * shift(t, S_ROLL)
                var ex = g[0]
                var ey = g[1]
                var hx = g[2]
                var hy = g[3]
                if (ev[0] >= 3f) {
                    // Hears something: that ear turns first, then head and eyes, gliding.
                    val s = if (ev[0] == 3f) -1f else 1f
                    val ear = hap * 0.35f * envAHR(x, 0.25f, 2.4f, 0.8f)
                    if (s < 0f) p[EAR_TW_L] += ear else p[EAR_TW_R] += ear
                    val wh = hap * envAHR(x - 0.4f, 0.9f, 1.4f, 0.9f)
                    ex += (s * 0.9f - ex) * wh; ey += (0.1f - ey) * wh
                    hx += (s * 0.75f - hx) * wh; hy += (0.1f - hy) * wh
                }
                p[BODY_ROLL] = roll
                p[LEAN] = sw * 0.012f * shift(t, S_LEAN)
                p[HEAD_YAW] = 0.25f * hx
                p[HEAD_PITCH] = 0.10f * hy + sw * 0.02f * wave(t, 97f, 1.1f)
                p[HEAD_ROLL] = -0.5f * roll + sw * 0.035f * wave(t, 83f, 0.2f)
                p[LOOK_X] = ex - 0.4f * hx; p[LOOK_Y] = ey - 0.4f * hy
                // Follow-through: when the head turns, the ears lag and swing after.
                val lag = clamp(g[2] - gLag[2], -1f, 1f)
                p[EAR_TW_L] -= 0.2f * lag; p[EAR_TW_R] -= 0.2f * lag
                p[EAR_L] = 0.2f + sw * 0.05f * wave(t, 131f, 0f)
                p[EAR_R] = 0.2f + sw * 0.05f * wave(t, 131f, 2.3f)
                p[TAIL_CURL] = 0.75f + sw * 0.04f * wave(t, 59f, 0.3f)
                p[PAW_LY] += sw * 0.006f * wave(t, 113f, 0f); p[PAW_RY] += sw * 0.006f * wave(t, 113f, 2.1f)
                if (ev[0] == 0f) {
                    // A stretch: leans well back more than it looks up, paws out.
                    val e = hap * envAHR(x, 1.0f, 0.7f, 1.7f)
                    p[LEAN] -= 0.05f * e; p[HEAD_PITCH] += 0.10f * e; eyeK = 1f - 0.55f * e
                    p[PAW_LX] -= 0.06f * e; p[PAW_RX] += 0.06f * e; p[PAW_LY] += 0.03f * e; p[PAW_RY] += 0.03f * e
                    p[EAR_L] -= 0.35f * e; p[EAR_R] -= 0.35f * e; p[TAIL_CURL] -= 0.12f * e
                    deepBreath = e
                } else if (ev[0] == 1f) {
                    // A tail flick (in tailAt); the tail uncurls a little with it.
                    p[TAIL_CURL] -= hap * 0.12f * bump(x / 1.5f)
                } else if (ev[0] == 2f) {
                    // A scratch at the side of its head (placed below).
                    scratch = hap * envAHR(x, 0.6f, 1.6f, 0.7f)
                    p[HEAD_ROLL] += 0.10f * scratch
                    eyeK = 1f - 0.45f * scratch
                }
                turnBlink = g[4]
            }
        }

        p[TAIL_SWING] = tailAt(state, t, o)
        p[TAIL_2] = tailAt(state, t - TAIL_LAG, o)
        p[TAIL_3] = tailAt(state, t - 2f * TAIL_LAG, o)
        p[TAIL_4] = tailAt(state, t - 3f * TAIL_LAG, o)
        p[TAIL_5] = tailAt(state, t - 4f * TAIL_LAG, o)

        val b = wave(t, breathK, 0f) * (1f + 0.6f * deepBreath)
        p[BREATH] = 1f + 0.018f * breathDepth * b
        p[BOB] = 0.007f * breathDepth * b + lift

        // Following the pointer: mostly with the eyes. Asleep, it does not.
        val w = if (state == FaceState.STANDBY) 0f else clamp(look.w, 0f, 1f)
        if (w > 0f) {
            val lx = clamp(look.x, -1f, 1f)
            val ly = clamp(look.y, -1f, 1f)
            p[LOOK_X] += (lx - p[LOOK_X]) * w
            p[LOOK_Y] += (ly - p[LOOK_Y]) * w
            p[HEAD_YAW] += o.head * 0.2f * lx * w
            p[HEAD_PITCH] += o.head * 0.2f * ly * w
        }

        if (scratch > 0f) {
            // Out round the cheek on the way, not through it.
            val q = onHead(p, 0.58f, 0.30f + 0.03f * wave(t, 2048f, 0f), -0.10f)
            val arc = 4f * scratch * (1f - scratch)
            p[PAW_RX] += (q[0] - p[PAW_RX]) * scratch + 0.10f * arc
            p[PAW_RY] += (q[1] - p[PAW_RY]) * scratch
            p[PAW_RZ] += (q[2] - p[PAW_RZ]) * scratch - 0.10f * arc
        }

        val k = eyeK * (1f - max(if (blinks) blinkAt(t, S_BLINK, blinkSlow, 2f, 10f) else 0f, turnBlink))
        p[EYE_L] *= k
        p[EYE_R] *= k
        return p
    }

    /**
     * One change of state the host remembers: the [state] that was LEFT, how
     * long it had been showing ([gap], seconds) and the loudness it was drawn
     * with when it was left ([amp]). See the desktop's makePose().
     */
    data class Change(val state: FaceState, val gap: Float, val amp: Float)

    /**
     * What the host remembered when the state changed - see the desktop's
     * `makePose()` for why each is needed.
     *
     * @param past the changes before this one, newest first ([Change]); the
     *   first is the change from [pose]'s `prevState`. With it, three or four
     *   changes inside a second or two all carry on smoothly. A host keeps it
     *   by putting `Change(oldState, now - changedAt, lastLoudness)` on the
     *   front at each change and dropping entries older than about twenty
     *   seconds. When it is given, the four below are not read.
     * @param prev2 the state before the previous one (null: none).
     * @param gap seconds the previous state had been showing when it ended.
     * @param prevAmp the loudness at the change (NaN: use the current one).
     * @param prevAmp2 the loudness at the change BEFORE that one - what
     *   [prev2] was drawn with. NaN: use [prevAmp].
     */
    data class Hist(
        val prev2: FaceState? = null,
        val gap: Float = 1e9f,
        val prevAmp: Float = Float.NaN,
        val prevAmp2: Float = Float.NaN,
        val past: List<Change>? = null,
    )

    /**
     * Each pose number's half-life, whether it swings a little past, and -
     * the desktop's `[hl, bouncy, cut, own]` - [cut]: an angle that settles
     * round the circle without passing through that angle (NaN: not an
     * angle); [own]: not slowed while falling asleep or waking.
     */
    internal class HalfLives(
        val hl: FloatArray,
        val bouncy: BooleanArray,
        val cut: FloatArray = FloatArray(hl.size) { Float.NaN },
        val own: BooleanArray = BooleanArray(hl.size),
    ) {
        // Worked out on use, so a table adjusted after it is made (the owl's orb) counts.
        val longest: Float get() = 8f * (hl.maxOrNull() ?: HL_BODY)
    }
    internal fun halfLives(n: Int, eyes: IntArray, mouth: IntArray, head: IntArray, limbs: IntArray, trail: IntArray): HalfLives {
        val hl = FloatArray(n) { HL_BODY }
        val bouncy = BooleanArray(n)
        for (i in eyes) hl[i] = HL_EYES
        for (i in mouth) hl[i] = HL_MOUTH
        for (i in head) hl[i] = HL_HEAD
        for (i in limbs) hl[i] = HL_LIMB
        for (i in trail) { hl[i] = HL_TRAIL; bouncy[i] = true }
        return HalfLives(hl, bouncy)
    }
    private val HALF = halfLives(
        N,
        intArrayOf(EYE_L, EYE_R, LOOK_X, LOOK_Y), intArrayOf(SPEAK), intArrayOf(HEAD_YAW, HEAD_PITCH, HEAD_ROLL, BROW),
        intArrayOf(PAW_LX, PAW_LY, PAW_LZ, PAW_RX, PAW_RY, PAW_RZ, ORB_X, ORB_Y, ORB_Z),
        intArrayOf(EAR_L, EAR_R, EAR_TW_L, EAR_TW_R, TAIL_SWING, TAIL_CURL, TAIL_2, TAIL_3, TAIL_4, TAIL_5),
    )

    /** The pose shown: the new state's, plus what is left of the changes before it (see [blend]). */
    fun pose(
        state: FaceState,
        prevState: FaceState,
        since: Float,
        t: Float,
        amp: Float,
        look: Look = Look(),
        hist: Hist = Hist(),
        opts: Opts = Opts(),
    ): FloatArray = blend(::stateTargets, HALF, state, prevState, since, t, amp, look, hist, opts)

    private const val LN2 = 0.6931471805599453f
    private const val FD = 1f / 120f
    private const val HIST_MAX = 6

    /** How much slower than usual a change from [prev] to [state] settles (the desktop's slowBy). */
    private fun slowBy(state: FaceState, prev: FaceState): Float = when {
        state == FaceState.STANDBY -> 5f
        prev == FaceState.STANDBY -> 2.5f
        state == FaceState.BANKED || prev == FaceState.BANKED -> 2f
        else -> 1f
    }

    /** The changes before this one, newest first, from either form of [hist] (the desktop's pastOf). */
    private fun pastOf(prevState: FaceState, hist: Hist, amp: Float): List<Change> {
        hist.past?.let { return it }
        val a0 = if (hist.prevAmp.isNaN()) amp else hist.prevAmp
        val first = Change(prevState, hist.gap, a0)
        val p2 = hist.prev2 ?: return listOf(first)
        return listOf(first, Change(p2, 1e9f, if (hist.prevAmp2.isNaN()) a0 else hist.prevAmp2))
    }

    /** What is left of an offset [x0] moving at [v0], [s] seconds on, with half-life [hl]. */
    private fun offset(x0: Float, v0: Float, hl: Float, bouncy: Boolean, s: Float): Float {
        if (s >= 8f * hl) return 0f
        val y = 2f * LN2 / hl
        val j1 = v0 + x0 * y
        val e = exp(-y * s)
        return if (bouncy) e * (x0 * cos(y * s) + (j1 / y) * sin(y * s)) else e * (x0 + j1 * s)
    }

    private class Two(val a: FloatArray, val b: FloatArray?)
    /** An angle's difference taken the short way round, -pi..pi. */
    private fun turn(a: Float): Float = a - TAU * kotlin.math.round(a / TAU)
    /** The same angle, somewhere in (c - 2pi, c]. */
    private fun below(a: Float, c: Float): Float = a - TAU * kotlin.math.ceil((a - c) / TAU)

    /**
     * Any animal's settling into a new state - the desktop's `makePose`:
     * inertialization, after Daniel Holden's Spring-It-On (inertialization.c,
     * decay_spring_damper_exact; MIT). The owl ([OwlPose]) and the otter
     * ([OtterPose]) use it too.
     */
    internal fun blend(
        targets: (FaceState, Float, Float, Look, Float, Opts) -> FloatArray,
        half: HalfLives,
        state: FaceState,
        prevState: FaceState,
        since: Float,
        t: Float,
        amp: Float,
        look: Look,
        hist: Hist,
        opts: Opts = Opts(),
    ): FloatArray = level(targets, half, state, pastOf(prevState, hist, amp), 0, since, t, amp, look, opts.norm(), false).a

    // The pose `since` seconds after the change into [state] (past[i] is the
    // change it came from) and, when [both], FD seconds earlier too - the
    // desktop's level().
    private fun level(
        targets: (FaceState, Float, Float, Look, Float, Opts) -> FloatArray,
        half: HalfLives,
        state: FaceState,
        past: List<Change>,
        i: Int,
        since: Float,
        t: Float,
        amp: Float,
        look: Look,
        o: Opts,
        both: Boolean,
    ): Two {
        val cur = targets(state, t, amp, look, since, o)
        val curB = if (both) targets(state, t - FD, amp, look, since - FD, o) else null
        val pv = if (i < HIST_MAX && i < past.size) past[i] else null
        if (pv == null || pv.state == state) return Two(cur, curB)
        val k = slowBy(state, pv.state)
        if (since >= half.longest * k) return Two(cur, curB)
        val s = max(0f, since)
        val sB = max(0f, since - FD)
        val tc = t - s
        val on = level(targets, half, pv.state, past, i + 1, pv.gap, tc, pv.amp, look, o, true)
        val onB = on.b ?: on.a
        val nwA = targets(state, tc, amp, look, 0f, o)
        val nwB = targets(state, tc - FD, amp, look, -FD, o)
        val outA = FloatArray(cur.size)
        val outB = if (both) FloatArray(cur.size) else null
        for (j in cur.indices) {
            val hl = if (half.own[j]) half.hl[j] else half.hl[j] * k
            var x0 = on.a[j] - nwA[j]
            var v0 = ((on.a[j] - onB[j]) - (nwA[j] - nwB[j])) / FD
            val c = half.cut[j]
            if (!c.isNaN()) {
                x0 = below(on.a[j], c) - below(nwA[j], c)
                v0 = (turn(on.a[j] - onB[j]) - turn(nwA[j] - nwB[j])) / FD
            }
            outA[j] = cur[j] + offset(x0, v0, hl, half.bouncy[j], s)
            if (outB != null && curB != null) outB[j] = curB[j] + offset(x0, v0, hl, half.bouncy[j], sB)
        }
        return Two(outA, outB)
    }

    /**
     * The mouth to draw, [open, wide, round] each 0..1 - the desktop's
     * `mouthOf`. [mouth] is the mouth track sampled at what is being heard
     * right now (open, wide, round; see `audio/LipSync.kt`), scaled by how
     * much the pose is speaking ([speak]: 1 in SPEAKING, 0 elsewhere, settling
     * with the state). Null - no real voice playing: a typed answer, Quiet
     * mode, an answer kept on screen - keeps the mouth SHUT. An animal never
     * makes up mouth movements that match no sound.
     */
    internal fun mouthOf(speak: Float, mouth: FloatArray?): FloatArray {
        val w = clamp(speak, 0f, 1f)
        if (mouth == null || w <= 0f) return floatArrayOf(0f, 0f, 0f)
        return floatArrayOf(mouthCh(mouth, 0) * w, mouthCh(mouth, 1) * w, mouthCh(mouth, 2) * w)
    }
    private fun mouthCh(m: FloatArray, i: Int): Float {
        val v = if (i < m.size) m[i] else 0f
        return if (v.isNaN()) 0f else clamp(v, 0f, 1f)
    }

    /** How much this pose is speaking, 0..1 - what [uniforms] scales the mouth by. */
    fun speakingWeight(p: FloatArray): Float = clamp(p[SPEAK], 0f, 1f)

    // --- from a pose to the numbers the shader reads -----------------------

    // 3x3 matrices, row by row.
    internal fun rx(a: Float): FloatArray {
        val c = cos(a); val s = sin(a)
        return floatArrayOf(1f, 0f, 0f, 0f, c, -s, 0f, s, c)
    }
    internal fun ry(a: Float): FloatArray {
        val c = cos(a); val s = sin(a)
        return floatArrayOf(c, 0f, s, 0f, 1f, 0f, -s, 0f, c)
    }
    internal fun rz(a: Float): FloatArray {
        val c = cos(a); val s = sin(a)
        return floatArrayOf(c, -s, 0f, s, c, 0f, 0f, 0f, 1f)
    }
    internal fun mul(a: FloatArray, b: FloatArray): FloatArray {
        val o = FloatArray(9)
        for (r in 0 until 3) for (c in 0 until 3) {
            o[r * 3 + c] = a[r * 3] * b[c] + a[r * 3 + 1] * b[3 + c] + a[r * 3 + 2] * b[6 + c]
        }
        return o
    }
    internal fun apply(m: FloatArray, x: Float, y: Float, z: Float) = floatArrayOf(
        m[0] * x + m[1] * y + m[2] * z,
        m[3] * x + m[4] * y + m[5] * z,
        m[6] * x + m[7] * y + m[8] * z,
    )
    /** Row i of the inverse = column i of the rotation. */
    internal fun invRow(m: FloatArray, i: Int) = floatArrayOf(m[i], m[3 + i], m[6 + i])

    private val TAIL_WRAP = arrayOf(
        floatArrayOf(0.18f, 0.08f, 0.30f, 0.10f), floatArrayOf(0.46f, 0.10f, 0.20f, 0.15f),
        floatArrayOf(0.62f, 0.14f, -0.04f, 0.17f), floatArrayOf(0.58f, 0.22f, -0.28f, 0.16f),
        floatArrayOf(0.40f, 0.30f, -0.42f, 0.13f), floatArrayOf(0.20f, 0.38f, -0.46f, 0.08f),
    )
    private val TAIL_OUT = arrayOf(
        floatArrayOf(0.18f, 0.08f, 0.30f, 0.10f), floatArrayOf(0.46f, 0.12f, 0.32f, 0.15f),
        floatArrayOf(0.70f, 0.22f, 0.26f, 0.17f), floatArrayOf(0.84f, 0.40f, 0.12f, 0.16f),
        floatArrayOf(0.88f, 0.60f, -0.04f, 0.13f), floatArrayOf(0.82f, 0.78f, -0.16f, 0.08f),
    )

    private const val SEAT_Y = -0.90f

    // The tail's uniform names, made once rather than as a new string for
    // every segment on every frame.
    private val TAIL_NAMES = arrayOf("uTail0", "uTail1", "uTail2", "uTail3", "uTail4", "uTail5")

    /**
     * Uniform name to value, exactly as the desktop's `uniforms()` returns.
     * [mouth] is the voice's mouth shape now, or null - see [mouthOf].
     */
    fun uniforms(p: FloatArray, mouth: FloatArray? = null): Map<String, FloatArray> {
        val bodyPos = floatArrayOf(0f, SEAT_Y + p[BOB], 0f)
        // Leaning tips the top toward the camera; rolling tips it to the viewer's right.
        val bm = mul(rz(-p[BODY_ROLL]), rx(-p[LEAN]))
        fun toWorld(x: Float, y: Float, z: Float): FloatArray {
            val v = apply(bm, x, y, z)
            return floatArrayOf(bodyPos[0] + v[0], bodyPos[1] + v[1], bodyPos[2] + v[2])
        }

        val neck = toWorld(NECK[0], NECK[1], NECK[2])
        val hm = mul(bm, headTurn(p))

        fun ear(perk: Float, side: Float, tw: Float): FloatArray {
            // Droops outward only below level, rounded off near level (the desktop's note).
            val out = 0.38f - 0.22f * perk + 0.175f * (sqrt(perk * perk + 0.0025f) - perk)
            val fwd = 0.22f * perk
            return mul(rz(-side * out), mul(rx(fwd), ry(side * tw)))
        }
        val el = ear(p[EAR_L], -1f, p[EAR_TW_L])
        val er = ear(p[EAR_R], 1f, p[EAR_TW_R])

        val out = LinkedHashMap<String, FloatArray>()
        out["uBodyPos"] = bodyPos
        out["uBodyR0"] = invRow(bm, 0); out["uBodyR1"] = invRow(bm, 1); out["uBodyR2"] = invRow(bm, 2)
        out["uBreath"] = floatArrayOf(p[BREATH])
        out["uNeck"] = neck
        out["uHeadR0"] = invRow(hm, 0); out["uHeadR1"] = invRow(hm, 1); out["uHeadR2"] = invRow(hm, 2)
        out["uEarL0"] = invRow(el, 0); out["uEarL1"] = invRow(el, 1); out["uEarL2"] = invRow(el, 2)
        out["uEarR0"] = invRow(er, 0); out["uEarR1"] = invRow(er, 1); out["uEarR2"] = invRow(er, 2)
        out["uFace"] = floatArrayOf(clamp(p[EYE_L], 0f, 1.2f), clamp(p[EYE_R], 0f, 1.2f), p[BROW])
        out["uMouth"] = mouthOf(p[SPEAK], mouth)
        out["uLook"] = floatArrayOf(clamp(p[LOOK_X], -1f, 1f), clamp(p[LOOK_Y], -1f, 1f))
        out["uShL"] = toWorld(-0.24f, 0.48f, -0.10f)
        out["uShR"] = toWorld(0.24f, 0.48f, -0.10f)
        out["uPawL"] = toWorld(p[PAW_LX], p[PAW_LY], p[PAW_LZ])
        out["uPawR"] = toWorld(p[PAW_RX], p[PAW_RY], p[PAW_RZ])
        val orb = toWorld(p[ORB_X], p[ORB_Y], p[ORB_Z])
        out["uOrb"] = floatArrayOf(orb[0], orb[1], orb[2], p[ORB_R])
        out["uOrbGlow"] = floatArrayOf(clamp(p[ORB_GLOW], 0f, 1.5f))

        val curl = clamp(p[TAIL_CURL], 0f, 1f)
        // Each point's own swing: further out swings as the root did a moment ago.
        val sw = floatArrayOf(p[TAIL_SWING], p[TAIL_SWING], p[TAIL_2], p[TAIL_3], p[TAIL_4], p[TAIL_5])
        val base = TAIL_WRAP[0]
        for (i in 0 until 6) {
            val a = TAIL_WRAP[i]
            val b = TAIL_OUT[i]
            val s = sw[i]
            var x = b[0] + (a[0] - b[0]) * curl
            var y = b[1] + (a[1] - b[1]) * curl
            var z = b[2] + (a[2] - b[2]) * curl
            val k = i / 5f
            val ang = s * 0.45f * k
            val dx = x - base[0]
            val dz = z - base[2]
            x = base[0] + dx * cos(ang) - dz * sin(ang)
            z = base[2] + dx * sin(ang) + dz * cos(ang)
            // A smooth |s| (see the desktop's note).
            y += (sqrt(s * s + 0.0016f) - 0.04f) * 0.05f * k
            val w = toWorld(x, y, z)
            out[TAIL_NAMES[i]] = floatArrayOf(w[0], w[1], w[2], a[3])
        }
        return out
    }

    // --- where the sleeping "Zs" rise from (the desktop's overlay) ----------

    /**
     * A world point to the shader's screen - the desktop's project(): [x, y]
     * with y UP, in the shader's `p` units (0 at the middle, 1 at the edge:
     * on the phone 2r from the centre, half the 4r square the animal is drawn
     * over). [cam] is the animal's camera (target x, y, z, distance, pitch);
     * [yaw], [pitch] and [zoom] are the host's uYaw, uPit and uZoom.
     */
    internal fun project(x: Float, y: Float, z: Float, cam: FloatArray, yaw: Float, pitch: Float, zoom: Float): FloatArray {
        val cp = cos(pitch + cam[4])
        val sp = sin(pitch + cam[4])
        val cy = cos(yaw)
        val sy = sin(yaw)
        val d = cam[3]
        val rx0 = x - (cam[0] - d * cp * sy)
        val ry0 = y - (cam[1] + d * sp)
        val rz0 = z - (cam[2] - d * cp * cy)
        val dx = rx0 * cy - rz0 * sy
        val rz1 = rx0 * sy + rz0 * cy
        val dy = ry0 * cp + rz1 * sp
        val dz = -ry0 * sp + rz1 * cp
        val f = 3.1f * zoom / max(dz, 1e-3f)
        return floatArrayOf(dx * f, dy * f)
    }
    /** [asleep 0..1, x, y] for a world point - the desktop's overlayAt(). */
    internal fun overlayAt(asleep: Float, at: FloatArray, cam: FloatArray, yaw: Float, pitch: Float, zoom: Float): FloatArray {
        val q = project(at[0], at[1], at[2], cam, yaw, pitch, if (zoom > 0f) zoom else 1f)
        return floatArrayOf(clamp(asleep, 0f, 1f), q[0], q[1])
    }
    // The panda's camera (redpanda.sksl): target x, y, z, distance, pitch.
    private val CAM = floatArrayOf(0f, -0.08f, 0f, 3.35f, 0f)

    /**
     * Where the sleeping "Zs" rise from, and how much to show them: [asleep,
     * x, y]. `asleep` settles 0 -> 1 as it nods off (and back as it wakes);
     * x and y are in [project]'s units, for the host's own [yaw], [pitch] and
     * [zoom]. A point a little above and to one side of the head, carried
     * with it. The desktop's `overlay(P, view)`.
     */
    fun overlay(p: FloatArray, yaw: Float = 0f, pitch: Float = 0f, zoom: Float = 1f): FloatArray {
        val bm = mul(rz(-p[BODY_ROLL]), rx(-p[LEAN]))
        val h = onHead(p, 0.3f, 0.92f, 0.0f)
        val v = apply(bm, h[0], h[1], h[2])
        return overlayAt(p[ASLEEP], floatArrayOf(v[0], SEAT_Y + p[BOB] + v[1], v[2]), CAM, yaw, pitch, zoom)
    }

    // --- the sleeping "Zs" themselves (the desktop's ZS and zs()) -----------

    /**
     * The Zs' numbers - the desktop's `ZS`, number for number (critter-pose.js
     * says what each one is). `CritterPoseTest` checks them, and [zs]'s
     * answers, against the desktop's fixture (critter-zs-golden.json).
     */
    object Zs {
        const val EVERY = 1.6f
        const val JITTER = 0.1f
        const val SLOTS = 2560
        const val LIFE = 3.2f
        const val LIFE_VAR = 0.8f
        const val RISE = 0.30f
        const val RISE_MIN = 0.12f
        const val TOP = 0.80f
        const val OUT = 0.10f
        const val TRADE = 0.8f
        const val SWAY = 0.022f
        const val SIZE0 = 0.090f
        const val SIZE1 = 0.160f
        const val ALPHA = 0.9f
        const val FADE_IN = 0.15f
        const val FADE_OUT = 0.45f
        const val TILT = 0.22f
        const val CALM_DX = 0.02f
        const val CALM_DY = 0.05f
        const val CALM_SIZE = 0.12f
        const val CALM_ALPHA = 0.75f
        const val WIDTH = 0.8f
        const val STROKE = 0.18f
        const val LIGHTEN = 0.60f
        const val COUNT = 5

        /** Every number above by the desktop's name, for the test. */
        val all: Map<String, Float> = mapOf(
            "EVERY" to EVERY, "JITTER" to JITTER, "SLOTS" to SLOTS.toFloat(), "LIFE" to LIFE,
            "LIFE_VAR" to LIFE_VAR, "RISE" to RISE, "RISE_MIN" to RISE_MIN, "TOP" to TOP, "OUT" to OUT, "TRADE" to TRADE,
            "SWAY" to SWAY, "SIZE0" to SIZE0, "SIZE1" to SIZE1, "ALPHA" to ALPHA, "FADE_IN" to FADE_IN,
            "FADE_OUT" to FADE_OUT, "TILT" to TILT, "CALM_DX" to CALM_DX, "CALM_DY" to CALM_DY,
            "CALM_SIZE" to CALM_SIZE, "CALM_ALPHA" to CALM_ALPHA, "WIDTH" to WIDTH, "STROKE" to STROKE,
            "LIGHTEN" to LIGHTEN, "COUNT" to COUNT.toFloat(),
        )
    }

    /**
     * The Zs for one frame - the desktop's `zs(t, ov, calm)`: [Zs.COUNT]
     * letters of five numbers each, flat - x, y (the shader's units, y UP, like
     * [overlay]), height (same units), alpha 0..1 and lean (radians,
     * counter-clockwise with y up). The first is calm's one still z, then the
     * four rising ones; a letter not showing has alpha 0.
     *
     * [ov] is [overlay]'s answer with its `asleep` already multiplied by
     * whatever the host fades the Zs with (FaceFrame.zsW); [calm] is the eased
     * calm weight; [t] the pose's own clock.
     */
    fun zs(t: Float, ov: FloatArray, calm: Float): FloatArray {
        val out = FloatArray(Zs.COUNT * 5)
        val asleep = clamp(ov[0], 0f, 1f)
        val ax = ov[1]
        val ay = ov[2]
        val c = clamp(calm, 0f, 1f)
        val side = if (ax >= 0f) 1f else -1f
        out[0] = ax + side * Zs.CALM_DX
        out[1] = ay + Zs.CALM_DY
        out[2] = Zs.CALM_SIZE
        out[3] = Zs.CALM_ALPHA * asleep * c
        out[4] = -side * Zs.TILT * 0.8f
        val rise = clamp(Zs.TOP - ay, Zs.RISE_MIN, Zs.RISE)
        val outward = Zs.OUT + (Zs.RISE - rise) * Zs.TRADE
        // The clock within PERIOD (exact in a float), as the desktop does.
        val tl = t - PERIOD * floor(t / PERIOD)
        val kHi = floor((tl + Zs.JITTER) / Zs.EVERY).toInt()
        var i = 5
        for (k in kHi - 3..kHi) {
            val n = Math.floorMod(k, Zs.SLOTS)
            val h1 = hash01(n * 3 + 101)
            val h2 = hash01(n * 3 + 102)
            val h3 = hash01(n * 3 + 103)
            val born = k * Zs.EVERY + (h1 * 2f - 1f) * Zs.JITTER
            val life = Zs.LIFE + Zs.LIFE_VAR * h2
            val u = (tl - born) / life
            if (u <= 0f || u >= 1f) {
                out[i] = ax; out[i + 1] = ay; out[i + 2] = Zs.SIZE0; out[i + 3] = 0f; out[i + 4] = 0f
                i += 5
                continue
            }
            val fade = smooth(clamp(u / Zs.FADE_IN, 0f, 1f)) * smooth(clamp((1f - u) / Zs.FADE_OUT, 0f, 1f))
            val e = u * (1.4f - 0.4f * u)
            out[i] = ax + side * outward * e + Zs.SWAY * sin(TAU * (0.8f * u + h3))
            out[i + 1] = ay + rise * e
            out[i + 2] = Zs.SIZE0 + (Zs.SIZE1 - Zs.SIZE0) * u
            out[i + 3] = Zs.ALPHA * fade * asleep * (1f - c)
            out[i + 4] = -side * Zs.TILT * (0.6f + 0.4f * h3)
            i += 5
        }
        return out
    }
}
