package com.jarvis.client.face

import com.jarvis.client.FaceState
import com.jarvis.client.face.CritterPose.Look
import com.jarvis.client.face.CritterPose.apply
import com.jarvis.client.face.CritterPose.clamp
import com.jarvis.client.face.CritterPose.invRow
import com.jarvis.client.face.CritterPose.mul
import com.jarvis.client.face.CritterPose.rx
import com.jarvis.client.face.CritterPose.ry
import com.jarvis.client.face.CritterPose.rz
import kotlin.math.PI
import kotlin.math.cos
import kotlin.math.max
import kotlin.math.pow
import kotlin.math.sin

/**
 * The pygmy owl's body language - a line-for-line copy of the desktop's
 * `jarvis-desktop/src/critter-owl.js`, held to the same answers by
 * `critter-pose-golden.json` and `CritterPoseTest`, exactly as [CritterPose]
 * (the panda) is. Change one, change the other, re-run tools/gen_critters.py.
 *
 * Owls have no hands, so the orb floats beside it; the head does the talking.
 */
object OwlPose {

    private const val HEAD_YAW = 0
    private const val HEAD_PITCH = 1
    private const val HEAD_ROLL = 2
    private const val NECK_DROP = 3
    private const val BOB = 4
    private const val BREATH = 5
    private const val FLUFF = 6
    private const val EYE_L = 7
    private const val EYE_R = 8
    private const val BROW = 9
    private const val BEAK = 10
    private const val LOOK_X = 11
    private const val LOOK_Y = 12
    private const val WING_L = 13
    private const val WING_R = 14
    private const val ORB_X = 15
    private const val ORB_Y = 16
    private const val ORB_Z = 17
    private const val ORB_R = 18
    private const val ORB_GLOW = 19
    private const val N = 20

    private const val TAU = (2.0 * PI).toFloat()
    private val ORB_REST = floatArrayOf(0.50f, 0.30f, -0.30f, 0.09f)

    fun stateTargets(state: FaceState, t: Float, amp: Float, look: Look): FloatArray {
        val p = FloatArray(N)
        p[BREATH] = 1f; p[FLUFF] = 1f; p[EYE_L] = 1f; p[EYE_R] = 1f
        p[ORB_X] = ORB_REST[0]; p[ORB_Y] = ORB_REST[1] + 0.03f * sin(t * 1.4f); p[ORB_Z] = ORB_REST[2]
        p[ORB_R] = ORB_REST[3]; p[ORB_GLOW] = 0.55f
        var breathPeriod = 3.6f
        var breathDepth = 1f
        var blinks = true

        when (state) {
            FaceState.LISTENING -> {
                p[HEAD_ROLL] = 0.34f + 0.03f * sin(t * 1.2f)
                p[HEAD_PITCH] = 0.05f
                p[EYE_L] = 1.12f; p[EYE_R] = 1.12f
                p[BROW] = 0.8f
                p[FLUFF] = 1.02f
                p[LOOK_Y] = 0.1f
                p[HEAD_YAW] = 0.12f * amp * sin(t * 9.0f)
                p[ORB_X] = 0.42f; p[ORB_Y] = 0.45f; p[ORB_Z] = -0.40f
                p[ORB_GLOW] = 0.55f + 0.5f * amp
            }
            FaceState.THINKING -> {
                val a = t * 0.9f
                p[ORB_X] = 0.68f * cos(a); p[ORB_Y] = 1.02f + 0.08f * sin(a * 2.0f)
                p[ORB_Z] = -0.05f - 0.55f * sin(a)
                p[ORB_R] = 0.10f
                p[HEAD_ROLL] = 0.55f * sin(t * 0.55f)
                p[HEAD_YAW] = 0.45f * cos(a) * max(0f, sin(a))
                p[HEAD_PITCH] = 0.12f
                p[LOOK_X] = 0.9f * cos(a); p[LOOK_Y] = 0.35f
                p[BROW] = 0.3f
                p[ORB_GLOW] = 0.95f + 0.2f * sin(t * 2.6f)
            }
            FaceState.SPEAKING -> {
                p[BEAK] = clamp(amp * 1.4f, 0f, 1f)
                p[HEAD_PITCH] = 0.04f + 0.08f * amp
                p[HEAD_YAW] = 0.10f * sin(t * 0.7f)
                p[HEAD_ROLL] = 0.05f * sin(t * 0.9f)
                p[BROW] = 0.3f + 0.3f * amp
                p[ORB_GLOW] = 0.6f + 0.45f * amp
            }
            FaceState.APPROVAL -> {
                p[WING_R] = 1.25f + 0.30f * sin(t * 6.0f)
                p[EYE_L] = 1.1f; p[EYE_R] = 1.1f
                p[BROW] = 0.9f
                p[HEAD_ROLL] = -0.10f
                p[ORB_GLOW] = 0.9f
            }
            FaceState.STANDBY -> {
                p[EYE_L] = 0f; p[EYE_R] = 0f
                p[FLUFF] = 1.10f
                p[NECK_DROP] = 0.08f
                p[HEAD_PITCH] = -0.18f
                p[HEAD_ROLL] = 0.10f
                p[ORB_X] = 0.62f; p[ORB_Y] = -0.02f; p[ORB_Z] = -0.12f
                p[ORB_GLOW] = 0.15f
                breathPeriod = 5.5f; breathDepth = 1.8f; blinks = false
            }
            FaceState.ERROR -> {
                p[HEAD_ROLL] = -0.45f
                p[HEAD_PITCH] = 0.10f
                p[EYE_L] = 0.45f; p[EYE_R] = 1.05f
                p[BROW] = -0.4f
                p[LOOK_Y] = 0.3f
                p[WING_L] = 0.35f; p[WING_R] = 0.35f
                p[FLUFF] = 1.04f + 0.01f * sin(t * 11.0f)
                p[ORB_GLOW] = 0.35f
            }
            FaceState.BANKED -> {
                p[EYE_L] = 0.35f; p[EYE_R] = 0.35f
                p[HEAD_PITCH] = -0.12f
                p[FLUFF] = 1.05f
                p[LOOK_Y] = -0.2f
                p[ORB_GLOW] = 0.25f
                breathPeriod = 5.0f
            }
            FaceState.IDLE -> {
                p[LOOK_X] = 0.55f * sin(t * 0.29f) + 0.25f * sin(t * 0.77f + 1.3f)
                p[LOOK_Y] = 0.15f * sin(t * 0.43f)
                val glance = max(0f, sin(t * 0.21f - 1.0f))
                p[HEAD_YAW] = 0.45f * p[LOOK_X] + 0.55f * glance.pow(8)
                p[HEAD_PITCH] = 0.08f * p[LOOK_Y]
                p[HEAD_ROLL] = 0.05f * sin(t * 0.37f)
            }
        }

        val b = sin((t * TAU) / breathPeriod)
        p[BREATH] = 1f + 0.016f * breathDepth * b
        p[BOB] = 0.008f * breathDepth * b

        val w = if (state == FaceState.STANDBY) 0f else clamp(look.w, 0f, 1f)
        if (w > 0f) {
            val lx = clamp(look.x, -1f, 1f)
            val ly = clamp(look.y, -1f, 1f)
            p[LOOK_X] += (lx - p[LOOK_X]) * w
            p[LOOK_Y] += (ly - p[LOOK_Y]) * w
            p[HEAD_YAW] += 0.7f * lx * w
            p[HEAD_PITCH] += 0.25f * ly * w
        }

        if (blinks) {
            val k = 1f - CritterPose.blink(t)
            p[EYE_L] *= k
            p[EYE_R] *= k
        }
        return p
    }

    fun pose(
        state: FaceState,
        prevState: FaceState,
        since: Float,
        t: Float,
        amp: Float,
        look: Look = Look(),
        hist: CritterPose.Hist = CritterPose.Hist(),
    ): FloatArray = CritterPose.blend(::stateTargets, state, prevState, since, t, amp, look, hist)

    private const val SEAT_Y = -0.93f

    fun uniforms(p: FloatArray): Map<String, FloatArray> {
        val bodyPos = floatArrayOf(0f, SEAT_Y + p[BOB], 0f)
        val bm = rx(0f)
        fun toWorld(x: Float, y: Float, z: Float): FloatArray {
            val v = apply(bm, x, y, z)
            return floatArrayOf(bodyPos[0] + v[0], bodyPos[1] + v[1], bodyPos[2] + v[2])
        }
        val neck = toWorld(0f, 0.70f - p[NECK_DROP], -0.02f)
        val hm = mul(bm, mul(ry(-p[HEAD_YAW]), mul(rx(p[HEAD_PITCH]), rz(-p[HEAD_ROLL]))))
        fun wing(lift: Float, side: Float) = rz(side * clamp(lift, 0f, 1.6f))
        val wl = wing(p[WING_L], -1f)
        val wr = wing(p[WING_R], 1f)
        val orb = toWorld(p[ORB_X], p[ORB_Y], p[ORB_Z])
        return linkedMapOf(
            "uBodyPos" to bodyPos,
            "uBodyR0" to invRow(bm, 0), "uBodyR1" to invRow(bm, 1), "uBodyR2" to invRow(bm, 2),
            "uBreath" to floatArrayOf(p[BREATH], p[FLUFF]),
            "uNeck" to neck,
            "uHeadR0" to invRow(hm, 0), "uHeadR1" to invRow(hm, 1), "uHeadR2" to invRow(hm, 2),
            "uWingL0" to invRow(wl, 0), "uWingL1" to invRow(wl, 1), "uWingL2" to invRow(wl, 2),
            "uWingR0" to invRow(wr, 0), "uWingR1" to invRow(wr, 1), "uWingR2" to invRow(wr, 2),
            "uFace" to floatArrayOf(
                clamp(p[EYE_L], 0f, 1.2f), clamp(p[EYE_R], 0f, 1.2f), p[BROW], clamp(p[BEAK], 0f, 1f),
            ),
            "uLook" to floatArrayOf(clamp(p[LOOK_X], -1f, 1f), clamp(p[LOOK_Y], -1f, 1f)),
            "uOrb" to floatArrayOf(orb[0], orb[1], orb[2], p[ORB_R]),
            "uOrbGlow" to floatArrayOf(clamp(p[ORB_GLOW], 0f, 1.5f)),
        )
    }
}
