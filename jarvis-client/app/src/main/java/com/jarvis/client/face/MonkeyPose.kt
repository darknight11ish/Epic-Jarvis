package com.jarvis.client.face

import com.jarvis.client.FaceState
import com.jarvis.client.face.CritterPose.Look
import com.jarvis.client.face.CritterPose.Opts
import com.jarvis.client.face.CritterPose.apply
import com.jarvis.client.face.CritterPose.beat
import com.jarvis.client.face.CritterPose.blinkAt
import com.jarvis.client.face.CritterPose.bump
import com.jarvis.client.face.CritterPose.clamp
import com.jarvis.client.face.CritterPose.ease
import com.jarvis.client.face.CritterPose.envAHR
import com.jarvis.client.face.CritterPose.eyesClose
import com.jarvis.client.face.CritterPose.eyesOpen
import com.jarvis.client.face.CritterPose.happening
import com.jarvis.client.face.CritterPose.invRow
import com.jarvis.client.face.CritterPose.looks
import com.jarvis.client.face.CritterPose.mul
import com.jarvis.client.face.CritterPose.restingGaze
import com.jarvis.client.face.CritterPose.rx
import com.jarvis.client.face.CritterPose.ry
import com.jarvis.client.face.CritterPose.rz
import com.jarvis.client.face.CritterPose.shift
import com.jarvis.client.face.CritterPose.smooth
import com.jarvis.client.face.CritterPose.toward
import com.jarvis.client.face.CritterPose.wave
import kotlin.math.PI
import kotlin.math.cos
import kotlin.math.exp
import kotlin.math.floor
import kotlin.math.max
import kotlin.math.pow
import kotlin.math.sin
import kotlin.math.sqrt
import kotlin.math.tanh

/**
 * The monkey's body language - a line-for-line copy of the desktop's
 * `jarvis-desktop/src/critter-monkey.js`, held to the same answers by
 * `critter-pose-golden.json` and `CritterPoseTest`.
 *
 * It hangs by one arm (the viewer's right) from a vine across the top of the
 * picture and swings gently round its hand like a slow pendulum; the other
 * hand holds a banana, which is its orb. Asleep, it has climbed up and sits
 * on the vine, its tail curled round it, hugging its banana. The desktop's
 * file says more about each piece.
 */
object MonkeyPose {

    private const val HEAD_YAW = 0
    private const val HEAD_PITCH = 1
    private const val HEAD_ROLL = 2
    private const val SWING = 3
    private const val LEAN = 4
    private const val BREATH = 5
    private const val BOB = 6
    private const val EYE_L = 7
    private const val EYE_R = 8
    private const val BROW = 9
    private const val SPEAK = 10
    private const val LOOK_X = 11
    private const val LOOK_Y = 12
    private const val EAR_L = 13
    private const val EAR_R = 14
    private const val VINE_Y_K = 15
    private const val VINE_Z = 16
    private const val HANG_X = 17
    private const val HANG_Y = 18
    private const val HANG_Z = 19
    private const val DIP = 20
    private const val DIP_X = 21
    private const val GRIP = 22
    private const val A_HX = 23
    private const val A_HY = 24
    private const val A_HZ = 25
    private const val B_EX = 26
    private const val B_EY = 27
    private const val B_EZ = 28
    private const val B_HX = 29
    private const val B_HY = 30
    private const val B_HZ = 31
    private const val ORB_X = 32
    private const val ORB_Y = 33
    private const val ORB_Z = 34
    private const val ORB_R = 35
    private const val ORB_GLOW = 36
    private const val BAN_YAW = 37
    private const val BAN_ROLL = 38
    private const val BAN_PITCH = 39
    private const val LEG_LF = 40
    private const val LEG_LO = 41
    private const val LEG_LK = 42
    private const val LEG_RF = 43
    private const val LEG_RO = 44
    private const val LEG_RK = 45
    private const val TAIL_WRAP = 46
    private const val TAIL_1 = 47
    private const val TAIL_2 = 48
    private const val TAIL_3 = 49
    private const val TAIL_4 = 50
    private const val A_EX = 51
    private const val TAIL_CURL = 52
    private const val ASLEEP = 53
    private const val A_EY = 54
    private const val A_EZ = 55
    private const val N = 56

    // Where the hand holds the vine, and the vine's height there while it hangs.
    private const val GRIP_X = 0.46f
    private const val VINE_Y = 0.93f
    // The body's middle from the pivot, hanging and sitting; the vine sitting.
    // (It hangs beside its hand, not under it: its arm goes up past the side
    // of its head, outside the ear - the desktop's note.)
    private val HANG = floatArrayOf(-0.60f, -1.133f, -0.11f)
    private val SIT = floatArrayOf(-0.46f, 0.245f, 0.0f)
    private const val VINE_SIT = -0.405f
    private val NECK = floatArrayOf(0f, 0.185f, -0.01f)
    private val SH_A = floatArrayOf(0.16f, 0.12f, 0.02f)
    private val SH_B = floatArrayOf(-0.15f, 0.11f, 0.0f)
    private val ELB_B = floatArrayOf(-0.25f, -0.01f, -0.03f)
    private val HAND_B = floatArrayOf(-0.31f, -0.13f, -0.09f)
    private val BAN_AT = floatArrayOf(0.07f, -0.025f, -0.035f)
    private const val THIGH = 0.16f
    private const val SHIN = 0.16f
    // Arm A's upper arm and forearm (each), and which way its elbow bends
    // while it holds the vine.
    private const val ARM = 0.62f
    private const val ELBOW_MAX = 0.3f
    private val POLE = floatArrayOf(1f, -0.25f, 0.2f)
    // How much bigger the head is drawn than it is modelled (monkey.sksl's HEAD_S).
    private const val HEAD_S = 1.10f

    // The monkey's own dice.
    private const val S_GAZE = 224
    private const val S_EVENT = 240
    private const val S_ROLL = 248
    private const val S_LEAN = 216
    private const val S_BEAT = 232
    private const val S_BLINK = 212
    // scratch, banana, kick, swing, look round, tail curl
    private val EVENTS = floatArrayOf(10f, 16f, 20f, 16f, 20f, 18f)
    private const val SLOT = 16f
    private const val CHANCE = 0.85f

    /** Whether one of its idle happenings is playing at clock [t] - the desktop's busy(state, t). */
    fun busy(state: FaceState, t: Float): Boolean =
        state == FaceState.IDLE && CritterPose.playing(happening(t, SLOT, 0.5f, 5.5f, S_EVENT, CHANCE, EVENTS))

    private fun headTurn(p: FloatArray): FloatArray = mul(ry(-p[HEAD_YAW]), mul(rx(p[HEAD_PITCH]), rz(-p[HEAD_ROLL])))

    /** A point in the head's (unscaled) frame, in the body's frame. */
    private fun onHead(p: FloatArray, x: Float, y: Float, z: Float): FloatArray {
        val v = apply(headTurn(p), x * HEAD_S, y * HEAD_S, z * HEAD_S)
        return floatArrayOf(NECK[0] + v[0], NECK[1] + v[1], NECK[2] + v[2])
    }

    /** How much each state lets it swing (the desktop's SWING). */
    private fun swingOf(state: FaceState): Float = when (state) {
        FaceState.IDLE -> 1f
        FaceState.LISTENING -> 0.45f
        FaceState.THINKING -> 0.55f
        FaceState.SPEAKING -> 0.6f
        FaceState.APPROVAL -> 0.15f
        FaceState.STANDBY -> 0f
        FaceState.ERROR -> 0.1f
        FaceState.BANKED -> 0.4f
    }

    /** The pendulum swing at clock [t] (the desktop's swingAt). */
    private fun swingAt(state: FaceState, t: Float, o: Opts): Float {
        val k = swingOf(state)
        var a = 0.014f * (1f + 0.25f * wave(t, 41f, 1.3f))
        if (state == FaceState.IDLE) {
            val ev = happening(t, SLOT, 0.5f, 5.5f, S_EVENT, CHANCE, EVENTS)
            if (ev[0] == 3f) a += o.hap * 0.007f * envAHR(ev[1], 1.5f, 3.0f, 2.0f)
        }
        return k * o.sway * a * wave(t, 293f, 0f)
    }
    private const val TAIL_LAG = 0.14f

    /** Which way a happening starting at clock [at] looks, 0..1 (the desktop's sideOf). */
    private fun sideOf(at: Float): Float = CritterPose.hash01((floor(at / SLOT).toInt() and 255) * 256 + S_EVENT + 3)

    fun stateTargets(state: FaceState, t: Float, amp: Float, look: Look, since: Float = 1e9f, o: Opts = Opts()): FloatArray {
        val hap = o.hap
        val sw = o.sway
        val play = o.play
        val p = FloatArray(N)
        p[BREATH] = 1f; p[EYE_L] = 1f; p[EYE_R] = 1f
        p[VINE_Y_K] = VINE_Y; p[VINE_Z] = 0.16f; p[HANG_X] = HANG[0]; p[HANG_Y] = HANG[1]; p[HANG_Z] = HANG[2]
        p[DIP] = 0.035f; p[DIP_X] = GRIP_X
        p[GRIP] = 1f; p[A_HX] = 0.20f; p[A_HY] = 0.05f; p[A_HZ] = -0.12f; p[A_EX] = 0.34f; p[A_EY] = -0.02f; p[A_EZ] = -0.06f
        p[B_EX] = ELB_B[0]; p[B_EY] = ELB_B[1]; p[B_EZ] = ELB_B[2]
        p[B_HX] = HAND_B[0]; p[B_HY] = HAND_B[1]; p[B_HZ] = HAND_B[2]
        p[ORB_R] = 0.09f; p[ORB_GLOW] = 0.55f; p[BAN_YAW] = 0.25f; p[BAN_ROLL] = 0.10f
        p[LEG_LF] = 0.18f; p[LEG_LO] = 0.10f; p[LEG_LK] = 0.45f
        p[LEG_RF] = 0.18f; p[LEG_RO] = 0.10f; p[LEG_RK] = 0.45f
        p[ASLEEP] = if (state == FaceState.STANDBY) 1f else 0f
        // 244 cycles a loop: a breath every 4.2 seconds.
        var breathK = 244f
        var breathDepth = 1f
        var blinkSlow = 1f
        var blinks = true
        var turnBlink = 0f
        var eyeK = 1f
        var deepBreath = 0f
        var scratch = 0f
        var peel = 0f

        when (state) {
            FaceState.LISTENING -> {
                // Leans in, head tilted, ears turned forward, eyes on you.
                val g = looks(t, S_GAZE, 1.8f, 6f, 0.8f, 0.2f, 0.1f, 0f, 0.05f, 1.1f, o)
                p[HEAD_ROLL] = play * 0.26f + sw * 0.025f * wave(t, 205f, 0f)
                p[HEAD_PITCH] = 0.06f
                p[HEAD_YAW] = 0.1f * g[2]
                p[LEAN] = 0.09f
                p[EAR_L] = -0.22f - 0.06f * amp; p[EAR_R] = p[EAR_L]
                p[EYE_L] = 1f + 0.12f * play; p[EYE_R] = p[EYE_L]
                p[BROW] = 0.3f + 0.4f * play
                p[LOOK_X] = g[0] - 0.4f * g[2]; p[LOOK_Y] = 0.1f + g[1] - 0.4f * g[3]
                p[ORB_GLOW] = 0.55f + 0.5f * amp
                turnBlink = g[4]
            }
            FaceState.THINKING -> {
                // The banana up in front of its chest, tapped in little bursts.
                val gate = smooth(clamp(0.5f + 1.5f * wave(t, 184f, 0f), 0f, 1f))
                val tap = sw * (0.5f - 0.5f * wave(t, 1141f, (PI / 2).toFloat())).pow(2) * gate
                val g = looks(t, S_GAZE, 1.8f, 6f, 0.55f, 0.6f, 0.2f, 0.75f, 0.05f, 1.1f, o)
                p[B_EX] = -0.24f; p[B_EY] = 0.02f; p[B_EZ] = -0.14f
                p[B_HX] = -0.10f; p[B_HY] = 0.02f + 0.045f * tap; p[B_HZ] = -0.27f
                p[BAN_YAW] = 0.1f + sw * 0.12f * wave(t, 97f, 0f); p[BAN_ROLL] = 0.35f; p[BAN_PITCH] = -0.2f
                p[ORB_R] = 0.11f
                p[HEAD_PITCH] = -0.30f + sw * 0.03f * wave(t, 147f, 0f) + 0.22f * g[3]
                p[HEAD_YAW] = -0.08f + 0.15f * g[2]
                p[HEAD_ROLL] = sw * 0.08f * wave(t, 98f, 0f)
                p[LOOK_X] = -0.2f + g[0] - 0.4f * g[2]
                p[LOOK_Y] = -0.7f + g[1] - 0.4f * g[3]
                p[BROW] = 0.25f
                p[LEAN] = 0.05f
                p[ORB_GLOW] = 0.95f + 0.2f * wave(t, 424f, 0f)
                turnBlink = g[4]
            }
            FaceState.SPEAKING -> {
                // Talks with its eyes, head and banana hand, in phrases (beat()).
                val g = looks(t, S_GAZE, 1.6f, 5.5f, 0.65f, 0.5f, 0.18f, 0f, 0.06f, 1.1f, o)
                val b = beat(t, S_BEAT, S_GAZE, 1.6f, 5.5f, 0.65f)
                val x = b[1]
                p[SPEAK] = 1f
                p[LEAN] = 0.05f
                p[HEAD_PITCH] = 0.03f
                p[HEAD_YAW] = sw * 0.05f * wave(t, 111f, 0f) + 0.09f * g[2]
                p[HEAD_ROLL] = sw * 0.04f * wave(t, 93f, 0.5f)
                p[LOOK_X] = g[0] - 0.16f * g[2]; p[LOOK_Y] = g[1] - 0.16f * g[3]
                p[BROW] = 0.3f + 0.1f * amp
                p[ORB_GLOW] = 0.6f + 0.45f * amp
                if (b[0] == 0f) {
                    p[HEAD_PITCH] -= hap * 0.065f * (bump(x / 0.7f) - 0.3f * bump((x - 0.55f) / 0.7f))
                    p[BROW] += hap * 0.25f * bump(x / 0.7f)
                } else if (b[0] == 1f) {
                    val e = hap * envAHR(x, 0.4f, 0.3f, 0.6f)
                    p[B_HX] += 0.05f * e; p[B_HY] += 0.12f * e; p[B_HZ] -= 0.08f * e
                    p[B_EY] += 0.05f * e; p[B_EZ] -= 0.03f * e
                    p[BAN_ROLL] += 0.25f * e
                    p[HEAD_PITCH] -= hap * 0.025f * bump(x / 0.9f)
                } else if (b[0] == 2f) {
                    p[HEAD_ROLL] += hap * play * 0.07f * bump(x / 1.2f)
                    p[BROW] += hap * 0.15f * bump(x / 1.2f)
                }
                turnBlink = g[4]
            }
            FaceState.APPROVAL -> {
                // Hangs still, leans in, looks at you, banana held out a little. No wave.
                val g = restingGaze(t, S_GAZE)
                p[LEAN] = 0.07f
                p[HEAD_PITCH] = 0.04f
                p[EYE_L] = 1f + 0.1f * play; p[EYE_R] = p[EYE_L]
                p[BROW] = 0.4f
                p[EAR_L] = -0.18f; p[EAR_R] = -0.18f
                p[B_EX] = -0.26f; p[B_EY] = 0.02f; p[B_EZ] = -0.10f
                p[B_HX] = -0.22f; p[B_HY] = -0.02f; p[B_HZ] = -0.30f
                p[BAN_YAW] = 0.35f; p[BAN_ROLL] = 0.05f
                p[LOOK_X] = g[0]; p[LOOK_Y] = g[1]
                p[ORB_GLOW] = 0.9f
                blinkSlow = 1.4f
            }
            FaceState.STANDBY -> {
                // Asleep, sitting on the vine, tail round it, hugging its banana.
                val e = happening(t, 16f, 0.5f, 5.5f, S_EVENT, 0.35f, 1)
                val sigh = if (e[0] == 0f) bump(e[1] / 4.5f) else 0f
                p[VINE_Y_K] = VINE_SIT; p[VINE_Z] = 0f; p[HANG_X] = SIT[0]; p[HANG_Y] = SIT[1]; p[HANG_Z] = SIT[2]
                p[DIP] = 0.02f; p[DIP_X] = 0f
                p[GRIP] = 0f; p[A_HX] = 0.07f; p[A_HY] = -0.03f; p[A_HZ] = -0.20f; p[A_EX] = 0.25f; p[A_EY] = -0.07f; p[A_EZ] = -0.08f
                p[B_EX] = -0.17f; p[B_EY] = -0.03f; p[B_EZ] = -0.10f; p[B_HX] = -0.07f; p[B_HY] = -0.04f; p[B_HZ] = -0.20f
                p[BAN_YAW] = 0f; p[BAN_ROLL] = 0f; p[BAN_PITCH] = 0f
                p[LEG_LF] = 1.30f; p[LEG_RF] = 1.30f; p[LEG_LO] = 0.12f; p[LEG_RO] = 0.12f; p[LEG_LK] = 1.30f; p[LEG_RK] = 1.30f
                p[TAIL_WRAP] = 1f
                p[EYE_L] = 0f; p[EYE_R] = 0f
                p[HEAD_PITCH] = -0.34f - 0.035f * sigh
                p[HEAD_ROLL] = 0.14f * play
                p[LEAN] = 0.04f
                p[EAR_L] = 0.1f; p[EAR_R] = 0.1f
                p[ORB_GLOW] = 0.15f
                deepBreath = sigh
                breathK = 171f; breathDepth = 1.8f; blinks = false
            }
            FaceState.ERROR -> {
                // A still, concerned look; hangs almost still. Nothing comic.
                val g = restingGaze(t, S_GAZE)
                p[HEAD_ROLL] = -0.12f * play
                p[HEAD_PITCH] = -0.10f
                p[EAR_L] = 0.15f; p[EAR_R] = 0.15f
                p[EYE_L] = 0.8f; p[EYE_R] = 0.8f
                p[BROW] = -0.3f
                p[LOOK_X] = g[0]; p[LOOK_Y] = -0.3f + g[1]
                p[ORB_GLOW] = 0.35f
                blinkSlow = 1.4f
            }
            FaceState.BANKED -> {
                // Dozing where it hangs; now and then its head sinks and it catches itself.
                val e = happening(t, 16f, 0.5f, 5.5f, S_EVENT, 0.55f, 1)
                val x = e[1]
                val droop = if (e[0] == 0f) {
                    if (x < 3.2f) smooth(clamp(x / 3.2f, 0f, 1f)) else 1f - smooth(clamp((x - 3.2f) / 0.8f, 0f, 1f))
                } else 0f
                p[EYE_L] = 0.35f * (1f - 0.7f * droop); p[EYE_R] = p[EYE_L]
                p[HEAD_PITCH] = -0.15f - 0.12f * droop
                p[EAR_L] = 0.1f; p[EAR_R] = 0.1f
                p[LOOK_Y] = -0.2f
                p[ORB_GLOW] = 0.25f
                breathK = 205f; blinkSlow = 2.5f
            }
            FaceState.IDLE -> {
                // Hangs and swings, looks about, and now and then one small thing.
                val g = looks(t, S_GAZE, 1.2f, 5f, 0.35f, 0.8f, 0.25f, 0f, 0.08f, 1.1f, o)
                val ev = happening(t, SLOT, 0.5f, 5.5f, S_EVENT, CHANCE, EVENTS)
                val x = ev[1]
                var ex = g[0]
                var ey = g[1]
                var hx = g[2]
                var hy = g[3]
                if (ev[0] == 4f) {
                    // Something to one side: that ear turns first, then head and eyes.
                    val s = if (sideOf(ev[2]) < 0.5f) -1f else 1f
                    val ear = hap * 0.35f * envAHR(x, 0.25f, 2.2f, 0.8f)
                    if (s < 0f) p[EAR_L] -= ear else p[EAR_R] -= ear
                    val wh = hap * envAHR(x - 0.4f, 0.9f, 1.3f, 0.9f)
                    ex += (s * 0.9f - ex) * wh; ey += (0.15f - ey) * wh
                    hx += (s * 0.75f - hx) * wh; hy += (0.1f - hy) * wh
                }
                p[LEAN] = sw * 0.015f * shift(t, S_LEAN)
                p[HEAD_YAW] = 0.25f * hx
                p[HEAD_PITCH] = 0.10f * hy + sw * 0.02f * wave(t, 97f, 1.1f)
                p[HEAD_ROLL] = sw * (0.03f * wave(t, 71f, 0.2f) + 0.025f * shift(t, S_ROLL))
                p[LOOK_X] = ex - 0.4f * hx; p[LOOK_Y] = ey - 0.4f * hy
                p[EAR_L] += sw * 0.04f * wave(t, 131f, 0f); p[EAR_R] += sw * 0.04f * wave(t, 131f, 2.3f)
                p[B_HY] += sw * 0.008f * wave(t, 113f, 0f)
                if (ev[0] == 0f) {
                    // Scratches the top of its head with its banana hand.
                    scratch = hap * envAHR(x, 0.6f, 1.5f, 0.7f)
                    p[HEAD_ROLL] += 0.05f * scratch
                    eyeK = 1f - 0.45f * scratch
                } else if (ev[0] == 1f) {
                    // Looks at its banana.
                    peel = hap * envAHR(x, 0.8f, 1.8f, 0.9f)
                    p[LOOK_X] += (-0.35f - p[LOOK_X]) * peel; p[LOOK_Y] += (-0.35f - p[LOOK_Y]) * peel
                    p[HEAD_YAW] += (-0.06f - p[HEAD_YAW]) * peel
                    p[HEAD_PITCH] += (-0.08f - p[HEAD_PITCH]) * peel
                    p[HEAD_ROLL] += 0.05f * peel
                } else if (ev[0] == 2f) {
                    // Kicks its legs, one then the other.
                    val e = hap * envAHR(x, 0.4f, 1.6f, 0.6f)
                    p[LEG_LF] += 0.28f * e * (0.5f + 0.5f * wave(t, 700f, 0f))
                    p[LEG_RF] += 0.28f * e * (0.5f + 0.5f * wave(t, 700f, PI.toFloat()))
                    p[LEG_LK] -= 0.2f * e; p[LEG_RK] -= 0.2f * e
                } else if (ev[0] == 5f) {
                    // Curls its tail tip tighter, and lets it go.
                    p[TAIL_CURL] += hap * 0.9f * envAHR(x, 0.7f, 1.0f, 1.0f)
                }
                turnBlink = g[4]
            }
        }

        // The swing, and what trails it (follow-through); the head stays more level.
        p[SWING] = swingAt(state, t, o)
        val s1 = swingAt(state, t - TAIL_LAG, o)
        val s2 = swingAt(state, t - 2f * TAIL_LAG, o)
        val s3 = swingAt(state, t - 3f * TAIL_LAG, o)
        val s4 = swingAt(state, t - 4f * TAIL_LAG, o)
        p[TAIL_1] = 0.9f * (s1 - p[SWING]); p[TAIL_2] = 1.4f * (s2 - p[SWING]); p[TAIL_3] = 1.9f * (s3 - p[SWING])
        p[TAIL_4] = 2.4f * (s4 - p[SWING])
        val tw = sw * 0.06f * wave(t, 77f, 0.9f)
        p[TAIL_2] += tw; p[TAIL_3] += 1.6f * tw; p[TAIL_4] += 2.0f * tw
        p[TAIL_CURL] += sw * 0.12f * wave(t, 59f, 0.3f)
        val legLag = 1.5f * (s2 - p[SWING])
        p[LEG_LO] -= legLag; p[LEG_RO] += legLag
        p[HEAD_ROLL] -= 0.4f * p[SWING]

        val b = wave(t, breathK, 0f) * (1f + 0.6f * deepBreath)
        p[BREATH] = 1f + 0.02f * breathDepth * b
        p[BOB] = 0.006f * breathDepth * b

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
            // The banana hand to the top of its head, swinging out round its side.
            val q = onHead(p, -0.24f, 0.66f + 0.025f * wave(t, 2048f, 0f), -0.05f)
            val arc = 4f * scratch * (1f - scratch)
            p[B_HX] += (q[0] - p[B_HX]) * scratch - 0.14f * arc
            p[B_HY] += (q[1] - p[B_HY]) * scratch
            p[B_HZ] += (q[2] - p[B_HZ]) * scratch - 0.06f * arc
            p[B_EX] += (-0.34f - p[B_EX]) * scratch; p[B_EY] += (0.26f - p[B_EY]) * scratch; p[B_EZ] += (-0.02f - p[B_EZ]) * scratch
            p[BAN_ROLL] += 1.2f * scratch
        }
        if (peel > 0f) {
            p[B_EX] += (-0.26f - p[B_EX]) * peel; p[B_EY] += (0.02f - p[B_EY]) * peel; p[B_EZ] += (-0.14f - p[B_EZ]) * peel
            p[B_HX] += (-0.14f - p[B_HX]) * peel; p[B_HY] += (0.10f - p[B_HY]) * peel; p[B_HZ] += (-0.30f - p[B_HZ]) * peel
            p[BAN_YAW] += 0.25f * peel * wave(t, 160f, 0f); p[BAN_ROLL] += 0.45f * peel
        }

        // The banana rides in the hand holding it.
        val off = apply(banFrame(p), BAN_AT[0], BAN_AT[1], BAN_AT[2])
        p[ORB_X] = p[B_HX] + off[0]; p[ORB_Y] = p[B_HY] + off[1]; p[ORB_Z] = p[B_HZ] + off[2]

        val qk = 1f - o.quiet
        val k = eyeK * (1f - qk * max(if (blinks) blinkAt(t, S_BLINK, blinkSlow, 2f, 9f) else 0f, turnBlink))
        p[EYE_L] *= k
        p[EYE_R] *= k
        return p
    }

    /** The banana's turn in the body's frame. */
    private fun banFrame(p: FloatArray): FloatArray = mul(ry(-p[BAN_YAW]), mul(rz(p[BAN_ROLL]), rx(p[BAN_PITCH])))

    /** How far a settling with half-life [hl] has got, [x] seconds in (the desktop's settled()). */
    private fun settled(x: Float, hl: Float): Float {
        val y = 2f * 0.6931471805599453f / hl
        return 1f - (1f + y * x) * exp(-y * x)
    }
    /** How far behind the vine is, for how far the monkey is from hanging (0) to sitting (1). */
    private fun behind(s: Float): Float = ease(s / 0.25f) * (1f - ease((s - 0.75f) / 0.25f))
    private const val VINE_BACK = 0.42f
    private fun passing(p: FloatArray, s: Float, cut: Float) {
        val b = VINE_BACK * behind(s) * cut
        p[VINE_Z] += b; p[HANG_Z] -= b
    }
    private fun hold(p: FloatArray, f: FloatArray, keys: IntArray, w: Float) {
        for (i in keys) p[i] = toward(p[i], f[i], w)
    }
    private val LEGS = intArrayOf(LEG_LF, LEG_LO, LEG_LK, LEG_RF, LEG_RO, LEG_RK)
    private val TAILK = intArrayOf(TAIL_WRAP, TAIL_1, TAIL_2, TAIL_3, TAIL_4, TAIL_CURL)
    private val HUG = intArrayOf(A_HX, A_HY, A_HZ, A_EX, A_EY, A_EZ, B_EX, B_EY, B_EZ, B_HX, B_HY, B_HZ, ORB_X, ORB_Y, ORB_Z, BAN_YAW, BAN_ROLL, BAN_PITCH)
    private val HEAD = intArrayOf(HEAD_YAW, HEAD_PITCH, HEAD_ROLL)

    /**
     * The monkey's climbing up to sleep and sliding down to wake - the
     * desktop's wakeSleep in critter-monkey.js, and its notes: the ordinary
     * settling makes the move; the vine always passes behind it; the extras
     * (holding on, legs, tail, banana and head in turn; a stretch and a flick
     * waking) play at ex times k, each from nothing.
     */
    private fun wakeSleep(p: FloatArray, state: FaceState, x: Float, k: Float, ex: Float, t: Float, f: FloatArray?) {
        val e = ex * k
        if (state == FaceState.STANDBY && f != null) {
            passing(p, 1f - k * (1f - settled(x, 0.9f)), 1f - ease((x - 2.2f) / 0.8f))
            val lids = (1f - 0.35f * ease((x - 0.1f) / 0.6f)) * (1f - ease((x - 1.9f) / 0.9f))
            val lid = k * toward(eyesClose(x), lids, ex)
            p[EYE_L] = f[EYE_L] * lid; p[EYE_R] = f[EYE_R] * lid
            p[GRIP] += e * f[GRIP] * settled(x, 0.75f) * (1f - ease((x - 1.0f) / 0.7f))
            hold(p, f, LEGS, e * settled(x, 1.1f) * (1f - ease((x - 1.0f) / 1.4f)))
            hold(p, f, TAILK, e * settled(x, 1.1f) * (1f - ease((x - 1.4f) / 1.4f)))
            hold(p, f, HUG, e * settled(x, 0.75f) * (1f - ease((x - 1.2f) / 1.4f)))
            hold(p, f, HEAD, e * settled(x, 0.65f) * (1f - ease((x - 1.6f) / 1.2f)))
            val up = e * envAHR(x, 0.4f, 0.5f, 0.6f)
            p[HEAD_PITCH] += 0.25f * up; p[LOOK_Y] += 0.6f * up
            return
        }
        passing(p, k * (1f - settled(x, 0.45f)), 1f - ease((x - 1.6f) / 0.6f))
        val lids = eyesOpen(x) * (1f - ex * bump((x - 0.75f) / 0.45f))
        val fe = 1f - k * (1f - lids)
        p[EYE_L] *= fe; p[EYE_R] *= fe
        val s = e * envAHR(x - 1.2f, 0.35f, 0.2f, 0.45f)
        p[LEG_LF] += 0.25f * s; p[LEG_RF] += 0.25f * s; p[LEG_LK] -= 0.2f * s; p[LEG_RK] -= 0.2f * s
        p[BREATH] += 0.012f * s; p[HEAD_PITCH] += 0.06f * s
        val flick = e * (bump((x - 1.2f) / 0.5f) - 0.3f * bump((x - 1.6f) / 0.5f))
        p[EAR_L] -= 0.3f * flick; p[EAR_R] -= 0.3f * flick
    }

    internal val HALF = CritterPose.halfLives(
        N,
        intArrayOf(EYE_L, EYE_R, LOOK_X, LOOK_Y), intArrayOf(SPEAK), intArrayOf(HEAD_YAW, HEAD_PITCH, HEAD_ROLL, BROW),
        intArrayOf(
            A_HX, A_HY, A_HZ, A_EX, A_EY, A_EZ, B_EX, B_EY, B_EZ, B_HX, B_HY, B_HZ, ORB_X, ORB_Y, ORB_Z,
            BAN_YAW, BAN_ROLL, BAN_PITCH, GRIP,
        ),
        intArrayOf(EAR_L, EAR_R, LEG_LF, LEG_LO, LEG_LK, LEG_RF, LEG_RO, LEG_RK, TAIL_1, TAIL_2, TAIL_3, TAIL_4, TAIL_CURL, TAIL_WRAP),
    )

    /** How much this pose is speaking, 0..1 - what [uniforms] scales the mouth by. */
    fun speakingWeight(p: FloatArray): Float = clamp(p[SPEAK], 0f, 1f)

    fun pose(
        state: FaceState,
        prevState: FaceState,
        since: Float,
        t: Float,
        amp: Float,
        look: Look = Look(),
        hist: CritterPose.Hist = CritterPose.Hist(),
        opts: Opts = Opts(),
    ): FloatArray = CritterPose.blend(::stateTargets, HALF, state, prevState, since, t, amp, look, hist, opts, ::wakeSleep, ASLEEP)

    // The tail hanging and wrapped round the vine (body frame; last: thickness).
    private val TAIL_HANG = arrayOf(
        floatArrayOf(0.00f, -0.16f, 0.11f, 0.036f), floatArrayOf(0.02f, -0.33f, 0.10f, 0.032f),
        floatArrayOf(0.02f, -0.50f, 0.06f, 0.030f), floatArrayOf(0.09f, -0.62f, 0.02f, 0.028f),
        floatArrayOf(0.14f, -0.54f, 0.01f, 0.026f),
    )
    private val TAIL_WRAP_AT = arrayOf(
        floatArrayOf(0.00f, -0.16f, 0.11f, 0.036f), floatArrayOf(0.12f, -0.23f, 0.12f, 0.032f),
        floatArrayOf(0.18f, -0.335f, 0.02f, 0.030f), floatArrayOf(0.21f, -0.26f, -0.08f, 0.028f),
        floatArrayOf(0.23f, -0.19f, -0.02f, 0.026f),
    )
    private const val HIP_X = 0.085f
    private const val HIP_Y = -0.13f
    private val TAIL_NAMES = arrayOf("uTail0", "uTail1", "uTail2", "uTail3", "uTail4")

    /** A leg's knee and foot (body frame): [kx, ky, kz, fx, fy, fz]. */
    private fun leg(side: Float, f: Float, o: Float, k: Float): FloatArray {
        val so = sin(o)
        val co = cos(o)
        val f2 = f - k
        val kx = side * HIP_X + THIGH * side * so * cos(f)
        val ky = HIP_Y - THIGH * co * cos(f)
        val kz = -THIGH * sin(f)
        return floatArrayOf(kx, ky, kz, kx + SHIN * side * so * cos(f2), ky - SHIN * co * cos(f2), kz - SHIN * sin(f2))
    }

    /** The vine's centre at x (monkey.sksl's partVine, without its thickness). */
    private fun vineAt(p: FloatArray, x: Float): Float {
        val dx = x - p[DIP_X]
        return p[VINE_Y_K] - 0.035f * x * x - p[DIP] / (1f + 18f * dx * dx)
    }

    /**
     * Where the elbow of an arm of two [ARM]-long pieces goes, from shoulder
     * [a] to hand [b], bending toward [pole] (world) - the desktop's bend().
     */
    private fun bend(a: FloatArray, b: FloatArray, pole: FloatArray): FloatArray {
        val dx = b[0] - a[0]
        val dy = b[1] - a[1]
        val dz = b[2] - a[2]
        // (Its direction eased where the hand passes close by the shoulder.)
        val len = sqrt(dx * dx + dy * dy + dz * dz)
        val ul = sqrt(len * len + 0.09f)
        val ux = dx / ul
        val uy = dy / ul
        val uz = dz / ul
        val k = pole[0] * ux + pole[1] * uy + pole[2] * uz
        val qx = pole[0] - k * ux
        val qy = pole[1] - k * uy
        val qz = pole[2] - k * uz
        // (Shrinks smoothly, rather than turning round, when the arm lines up with the pole.)
        val ql = sqrt(qx * qx + qy * qy + qz * qz + 0.09f)
        val slack = 2f * ARM - len
        val g = 0.5f * (slack + sqrt(slack * slack + 0.004f))
        val h = ELBOW_MAX * tanh(0.9f * g / ELBOW_MAX)
        return floatArrayOf(a[0] + dx / 2f + qx / ql * h, a[1] + dy / 2f + qy / ql * h, a[2] + dz / 2f + qz / ql * h)
    }

    /** The body's frame, and where its middle is (world). */
    private fun bodyMatrix(p: FloatArray): FloatArray = mul(rz(p[SWING]), rx(-p[LEAN]))
    private fun bodyPos(p: FloatArray): FloatArray {
        val h = apply(rz(p[SWING]), p[HANG_X], p[HANG_Y], p[HANG_Z])
        return floatArrayOf(GRIP_X + h[0], p[VINE_Y_K] + h[1] + p[BOB], p[VINE_Z] + h[2])
    }

    /** Uniform name to value; [mouth] as for [CritterPose.uniforms]. */
    fun uniforms(p: FloatArray, mouth: FloatArray? = null): Map<String, FloatArray> {
        val bm = bodyMatrix(p)
        val bodyPos = bodyPos(p)
        fun toWorld(x: Float, y: Float, z: Float): FloatArray {
            val v = apply(bm, x, y, z)
            return floatArrayOf(bodyPos[0] + v[0], bodyPos[1] + v[1], bodyPos[2] + v[2])
        }
        val hm = mul(bm, headTurn(p))
        val grip = clamp(p[GRIP], 0f, 1f)
        val free = toWorld(p[A_HX], p[A_HY], p[A_HZ])
        val onVine = floatArrayOf(GRIP_X, vineAt(p, GRIP_X) - 0.012f, p[VINE_Z] - 0.03f)
        val handA = floatArrayOf(
            free[0] + (onVine[0] - free[0]) * grip, free[1] + (onVine[1] - free[1]) * grip, free[2] + (onVine[2] - free[2]) * grip,
        )
        // Its elbow: bent out to the side while it holds the vine, else the pose's.
        val shA = toWorld(SH_A[0], SH_A[1], SH_A[2])
        val key = toWorld(p[A_EX], p[A_EY], p[A_EZ])
        val ik = bend(shA, handA, apply(bm, POLE[0], POLE[1], POLE[2]))
        val elbA = floatArrayOf(key[0] + (ik[0] - key[0]) * grip, key[1] + (ik[1] - key[1]) * grip, key[2] + (ik[2] - key[2]) * grip)
        val l = leg(-1f, p[LEG_LF], p[LEG_LO], p[LEG_LK])
        val r = leg(1f, p[LEG_RF], p[LEG_RO], p[LEG_RK])
        val ban = mul(bm, banFrame(p))
        val orb = toWorld(p[ORB_X], p[ORB_Y], p[ORB_Z])
        val out = LinkedHashMap<String, FloatArray>()
        out["uBodyPos"] = bodyPos
        out["uBodyR0"] = invRow(bm, 0); out["uBodyR1"] = invRow(bm, 1); out["uBodyR2"] = invRow(bm, 2)
        out["uBreath"] = floatArrayOf(p[BREATH])
        out["uNeck"] = toWorld(NECK[0], NECK[1], NECK[2])
        out["uHeadR0"] = invRow(hm, 0); out["uHeadR1"] = invRow(hm, 1); out["uHeadR2"] = invRow(hm, 2)
        out["uFace"] = floatArrayOf(clamp(p[EYE_L], 0f, 1.2f), clamp(p[EYE_R], 0f, 1.2f), p[BROW])
        out["uMouth"] = CritterPose.mouthOf(p[SPEAK], mouth)
        out["uLook"] = floatArrayOf(clamp(p[LOOK_X], -1f, 1f), clamp(p[LOOK_Y], -1f, 1f))
        out["uEars"] = floatArrayOf(clamp(p[EAR_L], -0.6f, 0.6f), clamp(p[EAR_R], -0.6f, 0.6f))
        out["uShA"] = shA
        out["uElbA"] = elbA
        out["uHandA"] = handA
        out["uShB"] = toWorld(SH_B[0], SH_B[1], SH_B[2])
        out["uElbB"] = toWorld(p[B_EX], p[B_EY], p[B_EZ])
        out["uHandB"] = toWorld(p[B_HX], p[B_HY], p[B_HZ])
        out["uKneeL"] = floatArrayOf(l[0], l[1], l[2]); out["uKneeR"] = floatArrayOf(r[0], r[1], r[2])
        out["uFootL"] = floatArrayOf(l[3], l[4], l[5]); out["uFootR"] = floatArrayOf(r[3], r[4], r[5])
        out["uVine"] = floatArrayOf(p[VINE_Y_K], p[VINE_Z], p[DIP_X], p[DIP])
        out["uBan0"] = invRow(ban, 0); out["uBan1"] = invRow(ban, 1); out["uBan2"] = invRow(ban, 2)
        out["uOrb"] = floatArrayOf(orb[0], orb[1], orb[2], p[ORB_R])
        out["uOrbGlow"] = floatArrayOf(clamp(p[ORB_GLOW], 0f, 1.5f))
        // The tail: each hanging segment turned by its own lag, the hook curled,
        // then blended toward the tail wrapped round the vine.
        val turns = floatArrayOf(0f, p[TAIL_1], p[TAIL_2], p[TAIL_3], p[TAIL_4])
        val wrap = clamp(p[TAIL_WRAP], 0f, 1f)
        var px = TAIL_HANG[0][0]
        var py = TAIL_HANG[0][1]
        for (i in 0 until 5) {
            val a = TAIL_HANG[i]
            val c = TAIL_WRAP_AT[i]
            var x = a[0]
            var y = a[1]
            if (i > 0) {
                val p0 = TAIL_HANG[i - 1]
                val ang = turns[i] + (if (i >= 3) 0.5f * p[TAIL_CURL] else 0f)
                val dx = a[0] - p0[0]
                val dy = a[1] - p0[1]
                val ca = cos(ang)
                val sa = sin(ang)
                x = px + dx * ca - dy * sa
                y = py + dx * sa + dy * ca
            }
            px = x; py = y
            val w = toWorld(x + (c[0] - x) * wrap, y + (c[1] - y) * wrap, a[2] + (c[2] - a[2]) * wrap)
            val thick = if (i < 4) 0.5f * (a[3] + TAIL_HANG[i + 1][3]) else a[3]
            out[TAIL_NAMES[i]] = floatArrayOf(w[0], w[1], w[2], thick)
        }
        return out
    }

    // The monkey's camera (monkey.sksl): target x, y, z, distance, pitch.
    private val CAM = floatArrayOf(-0.08f, 0.055f, 0f, 3.31f, 0f)

    /** Where its sleeping Zs rise from: [asleep, x, y] - see [CritterPose.overlay]. */
    fun overlay(p: FloatArray, yaw: Float = 0f, pitch: Float = 0f, zoom: Float = 1f): FloatArray {
        val bm = bodyMatrix(p)
        val bp = bodyPos(p)
        val h = onHead(p, 0.30f, 0.80f, 0.0f)
        val v = apply(bm, h[0], h[1], h[2])
        return CritterPose.overlayAt(p[ASLEEP], floatArrayOf(bp[0] + v[0], bp[1] + v[1], bp[2] + v[2]), CAM, yaw, pitch, zoom)
    }
}
