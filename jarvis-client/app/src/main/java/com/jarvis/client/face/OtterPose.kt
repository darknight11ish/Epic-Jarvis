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
import kotlin.math.max
import kotlin.math.pow
import kotlin.math.sin

/**
 * The sea otter's body language - a line-for-line copy of the desktop's
 * `jarvis-desktop/src/critter-otter.js`, held to the same answers by
 * `critter-pose-golden.json` and `CritterPoseTest`.
 *
 * It floats on its back: in the body's frame x runs along its spine (head at
 * -x), y points out of its belly and z is its side. The head keeps the frame
 * every animal's head has (face down -z), turned up toward the camera.
 */
object OtterPose {

    private const val HEAD_YAW = 0
    private const val HEAD_PITCH = 1
    private const val HEAD_ROLL = 2
    private const val BOB = 3
    private const val ROCK = 4
    private const val TILT = 5
    private const val BREATH = 6
    private const val EYE_L = 7
    private const val EYE_R = 8
    private const val PADDLE = 9
    private const val MOUTH = 10
    private const val LOOK_X = 11
    private const val LOOK_Y = 12
    private const val PAW_LX = 13
    private const val PAW_LY = 14
    private const val PAW_LZ = 15
    private const val PAW_RX = 16
    private const val PAW_RY = 17
    private const val PAW_RZ = 18
    private const val ORB_X = 19
    private const val ORB_Y = 20
    private const val ORB_Z = 21
    private const val ORB_R = 22
    private const val ORB_GLOW = 23
    private const val RIPPLE = 24
    private const val WAVE = 25
    private const val N = 26

    private const val TAU = (2.0 * PI).toFloat()
    private val NECK = floatArrayOf(-0.60f, 0.14f, 0.0f)
    private const val HEAD_BASE_YAW = 0.30f
    private const val HEAD_BASE_PITCH = 0.62f
    private val PEBBLE = floatArrayOf(-0.12f, 0.34f, 0.0f, 0.075f)

    private fun headTurn(p: FloatArray): FloatArray =
        mul(ry(-(HEAD_BASE_YAW + p[HEAD_YAW])), mul(rx(HEAD_BASE_PITCH + p[HEAD_PITCH]), rz(-p[HEAD_ROLL])))

    /** A point in the head's frame, in the body's frame. */
    private fun onHead(p: FloatArray, x: Float, y: Float, z: Float): FloatArray {
        val v = apply(headTurn(p), x, y, z)
        return floatArrayOf(NECK[0] + v[0], NECK[1] + v[1], NECK[2] + v[2])
    }

    private fun setPaw(p: FloatArray, base: Int, v: FloatArray) {
        p[base] = v[0]; p[base + 1] = v[1]; p[base + 2] = v[2]
    }

    fun stateTargets(state: FaceState, t: Float, amp: Float, look: Look): FloatArray {
        val p = FloatArray(N)
        p[TILT] = 0.10f; p[BREATH] = 1f; p[EYE_L] = 1f; p[EYE_R] = 1f
        p[PAW_LX] = -0.14f; p[PAW_LY] = 0.33f; p[PAW_LZ] = -0.09f
        p[PAW_RX] = -0.14f; p[PAW_RY] = 0.33f; p[PAW_RZ] = 0.09f
        p[ORB_X] = PEBBLE[0]; p[ORB_Y] = PEBBLE[1]; p[ORB_Z] = PEBBLE[2]; p[ORB_R] = PEBBLE[3]
        p[ORB_GLOW] = 0.55f; p[RIPPLE] = 0.010f
        p[WAVE] = t * 2.4f
        var breathPeriod = 4.2f
        var breathDepth = 1f
        var blinks = true
        var paws = ""

        when (state) {
            FaceState.LISTENING -> {
                p[TILT] = 0.24f
                p[HEAD_PITCH] = 0.12f
                p[HEAD_ROLL] = 0.28f + 0.03f * sin(t * 1.3f)
                p[EYE_L] = 1.12f; p[EYE_R] = 1.12f
                p[ORB_Y] = 0.30f
                p[ORB_GLOW] = 0.55f + 0.5f * amp
                paws = "cheeks"
            }
            FaceState.THINKING -> {
                val tap = max(0f, sin(t * 7.0f)).pow(3)
                p[ORB_Y] = PEBBLE[1] + 0.07f * tap
                p[PAW_LY] = 0.33f + 0.07f * tap; p[PAW_RY] = 0.33f + 0.07f * tap
                p[HEAD_PITCH] = -0.30f
                p[HEAD_ROLL] = 0.10f * sin(t * 0.6f)
                p[LOOK_Y] = -0.7f; p[LOOK_X] = 0.3f
                p[ORB_GLOW] = 0.95f + 0.2f * sin(t * 2.6f)
            }
            FaceState.SPEAKING -> {
                p[MOUTH] = clamp(amp * 1.35f, 0f, 1f)
                p[HEAD_PITCH] = 0.04f + 0.08f * amp
                p[HEAD_YAW] = 0.08f * sin(t * 0.7f)
                p[HEAD_ROLL] = 0.06f * sin(t * 0.9f)
                p[PAW_RX] = -0.22f; p[PAW_RY] = 0.42f + 0.08f * amp; p[PAW_RZ] = 0.14f
                p[ORB_GLOW] = 0.6f + 0.45f * amp
            }
            FaceState.APPROVAL -> {
                p[PAW_RX] = -0.32f + 0.07f * sin(t * 5.0f)
                p[PAW_RY] = 0.52f + 0.03f * sin(t * 10.0f)
                p[PAW_RZ] = 0.10f
                p[EYE_L] = 1.1f; p[EYE_R] = 1.1f
                p[HEAD_PITCH] = 0.10f
                p[ORB_GLOW] = 0.9f
            }
            FaceState.STANDBY -> {
                p[TILT] = 0.04f
                p[HEAD_PITCH] = 0.10f
                p[EYE_L] = 0f; p[EYE_R] = 0f
                p[ORB_GLOW] = 0.15f
                p[RIPPLE] = 0.005f
                breathPeriod = 6.0f; breathDepth = 1.8f; blinks = false
                paws = "eyes"
            }
            FaceState.ERROR -> {
                p[HEAD_ROLL] = -0.30f
                p[HEAD_PITCH] = 0.10f
                p[EYE_L] = 0.55f; p[EYE_R] = 0.9f
                p[LOOK_Y] = 0.3f
                p[ORB_X] = 0.12f; p[ORB_Y] = 0.26f; p[ORB_Z] = 0.20f
                p[ORB_GLOW] = 0.35f
                paws = "scratch"
            }
            FaceState.BANKED -> {
                p[EYE_L] = 0.35f; p[EYE_R] = 0.35f
                p[HEAD_PITCH] = -0.10f
                p[ORB_GLOW] = 0.25f
                breathPeriod = 5.0f
            }
            FaceState.IDLE -> {
                p[LOOK_X] = 0.55f * sin(t * 0.31f) + 0.25f * sin(t * 0.83f + 1.3f)
                p[LOOK_Y] = 0.15f * sin(t * 0.47f)
                p[HEAD_YAW] = 0.25f * p[LOOK_X]
                p[HEAD_PITCH] = 0.08f * p[LOOK_Y]
                p[HEAD_ROLL] = 0.06f * sin(t * 0.4f)
                p[PADDLE] = max(0f, sin(t * 0.7f)).pow(4) * (0.5f + 0.5f * sin(t * 6.0f))
            }
        }

        val swell = sin(t * 1.1f)
        p[BOB] = 0.018f * swell
        p[ROCK] += 0.05f * sin(t * 0.8f + 0.6f)
        val b = sin((t * TAU) / breathPeriod)
        p[BREATH] = 1f + 0.02f * breathDepth * b

        val w = if (state == FaceState.STANDBY) 0f else clamp(look.w, 0f, 1f)
        if (w > 0f) {
            val lx = clamp(look.x, -1f, 1f)
            val ly = clamp(look.y, -1f, 1f)
            p[LOOK_X] += (lx - p[LOOK_X]) * w
            p[LOOK_Y] += (ly - p[LOOK_Y]) * w
            p[HEAD_YAW] += 0.35f * lx * w
            p[HEAD_PITCH] += 0.2f * ly * w
        }

        when (paws) {
            "cheeks" -> {
                setPaw(p, PAW_LX, onHead(p, -0.24f, -0.08f, -0.10f))
                setPaw(p, PAW_RX, onHead(p, 0.24f, -0.08f, -0.10f))
            }
            "eyes" -> {
                setPaw(p, PAW_LX, onHead(p, -0.10f, 0.05f, -0.25f))
                setPaw(p, PAW_RX, onHead(p, 0.10f, 0.05f, -0.25f))
            }
            "scratch" -> {
                val s = 0.02f * sin(t * 9.0f)
                setPaw(p, PAW_LX, onHead(p, -0.25f + s, 0.14f, 0.02f))
            }
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

    private const val WATER_Y = -0.42f

    fun uniforms(p: FloatArray): Map<String, FloatArray> {
        val bodyPos = floatArrayOf(0.02f, WATER_Y + 0.02f + p[BOB], 0f)
        val bm = mul(rz(-p[TILT]), rx(p[ROCK]))
        fun toWorld(x: Float, y: Float, z: Float): FloatArray {
            val v = apply(bm, x, y, z)
            return floatArrayOf(bodyPos[0] + v[0], bodyPos[1] + v[1], bodyPos[2] + v[2])
        }
        val hm = mul(bm, headTurn(p))
        val orb = toWorld(p[ORB_X], p[ORB_Y], p[ORB_Z])
        return linkedMapOf(
            "uBodyPos" to bodyPos,
            "uBodyR0" to invRow(bm, 0), "uBodyR1" to invRow(bm, 1), "uBodyR2" to invRow(bm, 2),
            "uBreath" to floatArrayOf(p[BREATH]),
            "uNeck" to toWorld(NECK[0], NECK[1], NECK[2]),
            "uHeadR0" to invRow(hm, 0), "uHeadR1" to invRow(hm, 1), "uHeadR2" to invRow(hm, 2),
            "uFace" to floatArrayOf(
                clamp(p[EYE_L], 0f, 1.2f), clamp(p[EYE_R], 0f, 1.2f),
                clamp(p[PADDLE], 0f, 1f), clamp(p[MOUTH], 0f, 1f),
            ),
            "uLook" to floatArrayOf(clamp(p[LOOK_X], -1f, 1f), clamp(p[LOOK_Y], -1f, 1f)),
            "uShL" to toWorld(-0.34f, 0.20f, -0.13f),
            "uShR" to toWorld(-0.34f, 0.20f, 0.13f),
            "uPawL" to toWorld(p[PAW_LX], p[PAW_LY], p[PAW_LZ]),
            "uPawR" to toWorld(p[PAW_RX], p[PAW_RY], p[PAW_RZ]),
            "uWater" to floatArrayOf(WATER_Y, p[WAVE], clamp(p[RIPPLE], 0f, 0.03f), 0f),
            "uOrb" to floatArrayOf(orb[0], orb[1], orb[2], p[ORB_R]),
            "uOrbGlow" to floatArrayOf(clamp(p[ORB_GLOW], 0f, 1.5f)),
        )
    }
}
