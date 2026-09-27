package com.jarvis.client.face

import com.jarvis.client.FaceState
import kotlin.math.PI
import kotlin.math.abs
import kotlin.math.cos
import kotlin.math.floor
import kotlin.math.max
import kotlin.math.min
import kotlin.math.sin

/**
 * The red panda's body language: where its head, ears, eyes, paws, tail and
 * orb are on any frame, for any of Jarvis's eight states.
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
 * deterministic faces.
 *
 * Coordinates: x to the viewer's right, y up, the panda faces -z.
 */
object CritterPose {

    /** How long one pose takes to melt into the next, in seconds. */
    const val BLEND_S = 0.55f

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
    private const val MOUTH = 11
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
    private const val N = 27

    private const val TAU = (2.0 * PI).toFloat()

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

    /** 0 open .. 1 shut. A blink roughly every four seconds, never on a beat. */
    fun blink(t: Float): Float {
        val period = 4.1f
        val n = floor(t / period).toInt()
        val at = 0.4f + hash01(n) * 2.9f
        val x = t - n * period - at
        val len = 0.15f
        if (x < 0f || x > len) return 0f
        return sin((x / len) * PI.toFloat())
    }

    private fun clamp(v: Float, lo: Float, hi: Float) = max(lo, min(hi, v))
    private fun smooth(k: Float) = k * k * (3f - 2f * k)

    // Where things rest, in the body's own frame (origin on the seat).
    private val LAP_ORB = floatArrayOf(0f, 0.34f, -0.44f, 0.095f)
    private val LAP_PAW_L = floatArrayOf(-0.15f, 0.30f, -0.40f)
    private val LAP_PAW_R = floatArrayOf(0.15f, 0.30f, -0.40f)

    /** The pose for ONE state at clock [t]. See the desktop's stateTargets. */
    fun stateTargets(state: FaceState, t: Float, amp: Float, look: Look): FloatArray {
        val p = FloatArray(N)
        p[HEAD_YAW] = 0f; p[HEAD_PITCH] = 0f; p[HEAD_ROLL] = 0f; p[LEAN] = 0f; p[BOB] = 0f; p[BREATH] = 1f
        p[EAR_L] = 0.2f; p[EAR_R] = 0.2f; p[EYE_L] = 1f; p[EYE_R] = 1f; p[BROW] = 0f; p[MOUTH] = 0f
        p[LOOK_X] = 0f; p[LOOK_Y] = 0f
        p[PAW_LX] = LAP_PAW_L[0]; p[PAW_LY] = LAP_PAW_L[1]; p[PAW_LZ] = LAP_PAW_L[2]
        p[PAW_RX] = LAP_PAW_R[0]; p[PAW_RY] = LAP_PAW_R[1]; p[PAW_RZ] = LAP_PAW_R[2]
        p[TAIL_SWING] = 0f; p[TAIL_CURL] = 0.75f
        p[ORB_X] = LAP_ORB[0]; p[ORB_Y] = LAP_ORB[1]; p[ORB_Z] = LAP_ORB[2]; p[ORB_R] = LAP_ORB[3]
        p[ORB_GLOW] = 0.55f
        var breathPeriod = 4.0f
        var breathDepth = 1f
        var blinks = true

        when (state) {
            FaceState.LISTENING -> {
                p[HEAD_ROLL] = 0.26f + 0.03f * sin(t * 1.3f)
                p[HEAD_PITCH] = 0.06f
                p[LEAN] = 0.10f
                p[EAR_L] = 1f + 0.35f * amp * sin(t * 23.0f)
                p[EAR_R] = 1f + 0.35f * amp * sin(t * 19.0f + 1.1f)
                p[EYE_L] = 1.12f; p[EYE_R] = 1.12f
                p[BROW] = 0.7f
                p[LOOK_Y] = 0.1f
                p[TAIL_SWING] = 0.18f * sin(t * 1.6f)
                p[ORB_GLOW] = 0.55f + 0.5f * amp
            }
            FaceState.THINKING -> {
                val bob = 0.02f * sin(t * 2.2f)
                p[ORB_X] = 0f; p[ORB_Y] = 0.58f + bob; p[ORB_Z] = -0.56f; p[ORB_R] = 0.125f
                p[PAW_LX] = -0.12f; p[PAW_LY] = 0.50f + bob; p[PAW_LZ] = -0.52f
                p[PAW_RX] = 0.12f; p[PAW_RY] = 0.50f + bob; p[PAW_RZ] = -0.52f
                p[HEAD_PITCH] = -0.34f + 0.04f * sin(t * 0.9f)
                p[HEAD_ROLL] = 0.10f * sin(t * 0.6f)
                p[LOOK_X] = 0.2f * sin(t * 0.7f)
                p[LOOK_Y] = -0.7f
                p[EAR_L] = 0.05f; p[EAR_R] = 0.05f
                p[BROW] = 0.25f
                p[LEAN] = 0.06f
                p[TAIL_SWING] = 0.35f * sin(t * 1.7f)
                p[ORB_GLOW] = 0.95f + 0.2f * sin(t * 2.6f)
            }
            FaceState.SPEAKING -> {
                p[MOUTH] = clamp(amp * 1.35f, 0f, 1f)
                p[HEAD_PITCH] = 0.04f + 0.08f * amp
                p[HEAD_YAW] = 0.08f * sin(t * 0.7f)
                p[HEAD_ROLL] = 0.05f * sin(t * 0.9f)
                p[PAW_RX] = 0.24f; p[PAW_RY] = 0.42f + 0.07f * amp; p[PAW_RZ] = -0.46f
                p[BROW] = 0.3f + 0.3f * amp
                p[EAR_L] = 0.45f; p[EAR_R] = 0.45f
                p[TAIL_SWING] = 0.22f * sin(t * 1.2f)
                p[ORB_GLOW] = 0.6f + 0.45f * amp
            }
            FaceState.APPROVAL -> {
                p[PAW_LX] = -0.50f + 0.07f * sin(t * 5.0f)
                p[PAW_LY] = 1.00f + 0.03f * sin(t * 10.0f)
                p[PAW_LZ] = -0.48f
                p[EYE_L] = 1.1f; p[EYE_R] = 1.1f
                p[BROW] = 0.85f
                p[EAR_L] = 0.8f; p[EAR_R] = 0.8f
                p[HEAD_ROLL] = -0.10f
                p[HEAD_PITCH] = 0.05f
                p[TAIL_SWING] = 0.3f * sin(t * 2.0f)
                p[ORB_GLOW] = 0.9f
            }
            FaceState.STANDBY -> {
                p[EYE_L] = 0f; p[EYE_R] = 0f
                p[HEAD_PITCH] = -0.40f
                p[HEAD_ROLL] = 0.22f
                p[LEAN] = 0.06f
                p[EAR_L] = -0.7f; p[EAR_R] = -0.7f
                p[TAIL_CURL] = 1f
                p[TAIL_SWING] = 0.04f * sin(t * 0.5f)
                p[ORB_GLOW] = 0.15f
                breathPeriod = 6.0f; breathDepth = 1.8f; blinks = false
            }
            FaceState.ERROR -> {
                p[HEAD_ROLL] = -0.28f
                p[HEAD_PITCH] = 0.12f
                p[EAR_L] = -0.8f; p[EAR_R] = 0.5f
                p[EYE_L] = 0.55f; p[EYE_R] = 0.85f
                p[BROW] = -0.3f
                p[LOOK_Y] = 0.35f; p[LOOK_X] = -0.2f
                p[PAW_RX] = 0.44f + 0.02f * sin(t * 9.0f)
                p[PAW_RY] = 1.02f + 0.015f * sin(t * 9.0f + 1.0f)
                p[PAW_RZ] = -0.16f
                p[ORB_GLOW] = 0.35f
                p[TAIL_SWING] = 0.1f * sin(t * 0.8f)
            }
            FaceState.BANKED -> {
                p[EYE_L] = 0.35f; p[EYE_R] = 0.35f
                p[HEAD_PITCH] = -0.15f
                p[EAR_L] = -0.2f; p[EAR_R] = -0.2f
                p[LOOK_Y] = -0.2f
                p[ORB_GLOW] = 0.25f
                p[TAIL_CURL] = 0.9f
                breathPeriod = 5.0f
            }
            FaceState.IDLE -> {
                p[LOOK_X] = 0.55f * sin(t * 0.31f) + 0.25f * sin(t * 0.83f + 1.3f)
                p[LOOK_Y] = 0.15f * sin(t * 0.47f)
                p[HEAD_YAW] = 0.22f * p[LOOK_X]
                p[HEAD_PITCH] = 0.08f * p[LOOK_Y]
                p[HEAD_ROLL] = 0.06f * sin(t * 0.4f)
                p[TAIL_SWING] = 0.25f * sin(t * 0.9f)
            }
        }

        val b = sin((t * TAU) / breathPeriod)
        p[BREATH] = 1f + 0.018f * breathDepth * b
        p[BOB] = 0.010f * breathDepth * b

        val w = if (state == FaceState.STANDBY) 0f else clamp(look.w, 0f, 1f)
        if (w > 0f) {
            val lx = clamp(look.x, -1f, 1f)
            val ly = clamp(look.y, -1f, 1f)
            p[LOOK_X] += (lx - p[LOOK_X]) * w
            p[LOOK_Y] += (ly - p[LOOK_Y]) * w
            p[HEAD_YAW] += 0.35f * lx * w
            p[HEAD_PITCH] += 0.2f * ly * w
        }

        if (blinks) {
            val k = 1f - blink(t)
            p[EYE_L] *= k
            p[EYE_R] *= k
        }
        return p
    }

    /** The pose shown: the previous state's melting into the current one. */
    fun pose(
        state: FaceState,
        prevState: FaceState,
        since: Float,
        t: Float,
        amp: Float,
        look: Look = Look(),
    ): FloatArray {
        val cur = stateTargets(state, t, amp, look)
        val k = clamp(since / BLEND_S, 0f, 1f)
        if (k >= 1f || prevState == state) return cur
        val prev = stateTargets(prevState, t, amp, look)
        val e = smooth(k)
        return FloatArray(N) { prev[it] + (cur[it] - prev[it]) * e }
    }

    // --- from a pose to the numbers the shader reads -----------------------

    // 3x3 matrices, row by row.
    private fun rx(a: Float): FloatArray {
        val c = cos(a); val s = sin(a)
        return floatArrayOf(1f, 0f, 0f, 0f, c, -s, 0f, s, c)
    }
    private fun ry(a: Float): FloatArray {
        val c = cos(a); val s = sin(a)
        return floatArrayOf(c, 0f, s, 0f, 1f, 0f, -s, 0f, c)
    }
    private fun rz(a: Float): FloatArray {
        val c = cos(a); val s = sin(a)
        return floatArrayOf(c, -s, 0f, s, c, 0f, 0f, 0f, 1f)
    }
    private fun mul(a: FloatArray, b: FloatArray): FloatArray {
        val o = FloatArray(9)
        for (r in 0 until 3) for (c in 0 until 3) {
            o[r * 3 + c] = a[r * 3] * b[c] + a[r * 3 + 1] * b[3 + c] + a[r * 3 + 2] * b[6 + c]
        }
        return o
    }
    private fun apply(m: FloatArray, x: Float, y: Float, z: Float) = floatArrayOf(
        m[0] * x + m[1] * y + m[2] * z,
        m[3] * x + m[4] * y + m[5] * z,
        m[6] * x + m[7] * y + m[8] * z,
    )
    /** Row i of the inverse = column i of the rotation. */
    private fun invRow(m: FloatArray, i: Int) = floatArrayOf(m[i], m[3 + i], m[6 + i])

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

    /** Uniform name to value, exactly as the desktop's `uniforms()` returns. */
    fun uniforms(p: FloatArray): Map<String, FloatArray> {
        val bodyPos = floatArrayOf(0f, SEAT_Y + p[BOB], 0f)
        val bm = rx(-p[LEAN])
        fun toWorld(x: Float, y: Float, z: Float): FloatArray {
            val v = apply(bm, x, y, z)
            return floatArrayOf(bodyPos[0] + v[0], bodyPos[1] + v[1], bodyPos[2] + v[2])
        }

        val neck = toWorld(0f, 0.60f, -0.02f)
        val hm = mul(bm, mul(ry(-p[HEAD_YAW]), mul(rx(p[HEAD_PITCH]), rz(-p[HEAD_ROLL]))))

        fun ear(perk: Float, side: Float): FloatArray {
            val out = 0.38f - 0.22f * perk + (if (perk < 0f) -0.35f * perk else 0f)
            val fwd = 0.22f * perk
            return mul(rz(-side * out), rx(fwd))
        }
        val el = ear(p[EAR_L], -1f)
        val er = ear(p[EAR_R], 1f)

        val out = LinkedHashMap<String, FloatArray>()
        out["uBodyPos"] = bodyPos
        out["uBodyR0"] = invRow(bm, 0); out["uBodyR1"] = invRow(bm, 1); out["uBodyR2"] = invRow(bm, 2)
        out["uBreath"] = floatArrayOf(p[BREATH])
        out["uNeck"] = neck
        out["uHeadR0"] = invRow(hm, 0); out["uHeadR1"] = invRow(hm, 1); out["uHeadR2"] = invRow(hm, 2)
        out["uEarL0"] = invRow(el, 0); out["uEarL1"] = invRow(el, 1); out["uEarL2"] = invRow(el, 2)
        out["uEarR0"] = invRow(er, 0); out["uEarR1"] = invRow(er, 1); out["uEarR2"] = invRow(er, 2)
        out["uFace"] = floatArrayOf(
            clamp(p[EYE_L], 0f, 1.2f), clamp(p[EYE_R], 0f, 1.2f), p[BROW], clamp(p[MOUTH], 0f, 1f),
        )
        out["uLook"] = floatArrayOf(clamp(p[LOOK_X], -1f, 1f), clamp(p[LOOK_Y], -1f, 1f))
        out["uShL"] = toWorld(-0.24f, 0.48f, -0.10f)
        out["uShR"] = toWorld(0.24f, 0.48f, -0.10f)
        out["uPawL"] = toWorld(p[PAW_LX], p[PAW_LY], p[PAW_LZ])
        out["uPawR"] = toWorld(p[PAW_RX], p[PAW_RY], p[PAW_RZ])
        val orb = toWorld(p[ORB_X], p[ORB_Y], p[ORB_Z])
        out["uOrb"] = floatArrayOf(orb[0], orb[1], orb[2], p[ORB_R])
        out["uOrbGlow"] = floatArrayOf(clamp(p[ORB_GLOW], 0f, 1.5f))

        val s = p[TAIL_SWING]
        val curl = clamp(p[TAIL_CURL], 0f, 1f)
        val base = TAIL_WRAP[0]
        for (i in 0 until 6) {
            val a = TAIL_WRAP[i]
            val b = TAIL_OUT[i]
            var x = b[0] + (a[0] - b[0]) * curl
            var y = b[1] + (a[1] - b[1]) * curl
            var z = b[2] + (a[2] - b[2]) * curl
            val k = i / 5f
            val ang = s * 0.45f * k
            val dx = x - base[0]
            val dz = z - base[2]
            x = base[0] + dx * cos(ang) - dz * sin(ang)
            z = base[2] + dx * sin(ang) + dz * cos(ang)
            y += abs(s) * 0.05f * k
            val w = toWorld(x, y, z)
            out["uTail$i"] = floatArrayOf(w[0], w[1], w[2], a[3])
        }
        return out
    }
}
