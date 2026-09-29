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
import com.jarvis.client.face.CritterPose.happeningV
import com.jarvis.client.face.CritterPose.breathWave
import com.jarvis.client.face.CritterPose.noise
import com.jarvis.client.face.CritterPose.NONE4
import com.jarvis.client.face.CritterPose.playingV
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
import com.jarvis.client.face.CritterPose.NONE
import com.jarvis.client.face.CritterPose.ZERO2
import com.jarvis.client.face.CritterPose.ackGlowOf
import com.jarvis.client.face.CritterPose.ackNodOf
import com.jarvis.client.face.CritterPose.arrivalOf
import com.jarvis.client.face.CritterPose.awake
import com.jarvis.client.face.CritterPose.cuteAt
import com.jarvis.client.face.CritterPose.cuteBusy
import com.jarvis.client.face.CritterPose.cuteOf
import com.jarvis.client.face.CritterPose.cuteQuiet
import com.jarvis.client.face.CritterPose.switchE
import com.jarvis.client.face.CritterPose.focusEndOf
import com.jarvis.client.face.CritterPose.focusOf
import com.jarvis.client.face.CritterPose.fullTurn
import com.jarvis.client.face.CritterPose.gaze
import com.jarvis.client.face.CritterPose.listenNod
import com.jarvis.client.face.CritterPose.petOf
import com.jarvis.client.face.CritterPose.phraseBeat
import com.jarvis.client.face.CritterPose.variant
import kotlin.math.PI
import kotlin.math.floor
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
    private const val SPEAK = 10
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
    private const val ASLEEP = 26
    private const val LID = 27
    private const val LID_SLOPE = 28
    private const val N = 29

    private const val TAU = (2.0 * PI).toFloat()
    private val NECK = floatArrayOf(-0.60f, 0.14f, 0.0f)
    private const val HEAD_BASE_YAW = 0.30f
    private const val HEAD_BASE_PITCH = 0.62f
    private val PEBBLE = floatArrayOf(-0.12f, 0.34f, 0.0f, 0.075f)
    // Where the pebble lies when the paws have let go of it: down on the chest.
    private val PEBBLE_DOWN = PEBBLE[1] - 0.08f

    // The otter's own dice.
    private const val S_GAZE = 160
    private const val S_EVENT = 176
    private const val S_ROLL = 184
    private const val S_LEAN = 192
    private const val S_BEAT = 200
    private const val S_BLINK = 208
    // Its idle happenings, and how often each comes up (the desktop's EVENTS):
    // wash, roll left, roll right, kick, rub.
    private val EVENTS = floatArrayOf(14f, 20f, 20f, 20f, 26f)
    // ...and for the new behaviours (critter-pose.js's note).
    private const val S_LISTEN = 216
    private const val S_THINK = 219
    private const val S_FOCUS = 222
    private const val S_NOD = 234
    private const val S_PHRASE = 235
    private const val S_CUTE = 236
    // The otter's own seeds for the slow wander (noise()): its talking sway and its breathing.
    private const val N_YAW = 24
    private const val N_ROLL = 25
    private const val N_BREATH = 26
    /** How long each cute moment lasts: rolling over in the water, juggling its pebble from paw to paw. */
    private val CUTE_LEN = floatArrayOf(6.8f, 6.5f)

    /** Whether one of its idle happenings is playing at clock [t] - the desktop's busy(state, t). */
    fun busy(state: FaceState, t: Float, since: Float? = null, opts: Opts? = null): Boolean =
        state == FaceState.IDLE && (playingV(happeningV(t, 16f, 0.5f, 5.5f, S_EVENT, 0.7f, EVENTS, opts?.norm(t)?.attention ?: 1f)) ||
            cuteBusy(t, since, opts, S_CUTE, CUTE_LEN))

    /** Whether one of its own talking gestures is playing at clock [t] - the desktop's gesturing(t). */
    fun gesturing(t: Float): Boolean {
        val b = beat(t, S_BEAT, S_GAZE, 1.8f, 6f, 0.65f)
        return b[0] >= 0f && b[1] >= 0f && b[1] < CritterPose.GESTURE_S
    }

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

    fun stateTargets(state: FaceState, t: Float, amp: Float, look: Look, since: Float = 1e9f, o0: Opts = Opts()): FloatArray {
        val o = o0.norm(t)
        // Idle: a focus session, and a cute moment while it plays, take the happenings away.
        val cu = if (state == FaceState.IDLE) cuteAt(t, since, S_CUTE, CUTE_LEN) else NONE
        val cw = if (cu[0] >= 0f) cuteOf(o) else 0f
        val fw = if (state == FaceState.IDLE) focusOf(o) else 0f
        val fp = fw * (1f - 0.6f * o.calm)   // the focus pose itself: smaller under calm (the happenings still go by fw)
        // (and so do the stretch as a focus session ends, and being stroked)
        val fe = if (state == FaceState.IDLE) focusEndOf(t, o) else 0f
        val pw = if (awake(state)) petOf(o) else 0f
        // (The idle happening of this slot, its size and thinning: happeningV.)
        val evI = if (state == FaceState.IDLE) happeningV(t, 16f, 0.5f, 5.5f, S_EVENT, 0.7f, EVENTS, o.attention) else NONE4
        val hap = o.hap * (1f - fw) * (1f - cw * (if (cu[0] >= 0f) cuteQuiet(cu[1], CUTE_LEN[cu[0].toInt()]) else 0f)) * (1f - fe) * (1f - pw) * evI[3]
        val sw = o.sway
        val play = o.play
        val p = FloatArray(N)
        p[TILT] = 0.10f; p[BREATH] = 1f; p[EYE_L] = 1f; p[EYE_R] = 1f
        p[PAW_LX] = -0.14f; p[PAW_LY] = 0.33f; p[PAW_LZ] = -0.09f
        p[PAW_RX] = -0.14f; p[PAW_RY] = 0.33f; p[PAW_RZ] = 0.09f
        p[ORB_X] = PEBBLE[0]; p[ORB_Y] = PEBBLE[1]; p[ORB_Z] = PEBBLE[2]; p[ORB_R] = PEBBLE[3]
        p[ORB_GLOW] = 0.55f; p[RIPPLE] = 0.010f
        // Where the rings on the water have spread to (391 cycles a loop), kept small.
        val u = CritterPose.loopT(t) / CritterPose.LOOP * 391f
        p[WAVE] = TAU * (u - floor(u))
        p[ASLEEP] = if (state == FaceState.STANDBY) 1f else 0f
        // 244 cycles a loop: a breath every 4.2 seconds.
        var breathK = 244f
        var breathDepth = 1f
        var blinkSlow = 1f
        var blinks = true
        var turnBlink = 0f
        var calm = 1f
        var eyeK = 1f
        var deepBreath = 0f
        var pawsOnEyes = false
        var wash = 0f
        var ackK = 1f

        when (state) {
            FaceState.LISTENING -> {
                // Head up and tilted, eyes on you, its pebble held on its chest.
                val g = looks(t, S_GAZE, 2f, 7f, 0.8f, 0.2f, 0.1f, 0f, 0.05f, 1.1f, o)
                p[TILT] = 0.24f
                p[HEAD_PITCH] = 0.12f
                p[HEAD_YAW] = 0.1f * g[2]
                p[HEAD_ROLL] = play * 0.28f + sw * 0.025f * wave(t, 212f, 0f)
                p[EYE_L] = 1f + 0.12f * play; p[EYE_R] = p[EYE_L]
                p[LOOK_X] = g[0] - 0.4f * g[2]; p[LOOK_Y] = g[1] - 0.4f * g[3]
                p[ORB_GLOW] = 0.55f + 0.5f * amp
                // Now and then (variety): the other tilt, head lifted closer, a small kick.
                val v = variant(t, o, S_LISTEN, 0.4f)
                if (v[0] == 0f) p[HEAD_ROLL] -= 0.42f * play * v[1]
                else if (v[0] == 1f) { p[HEAD_PITCH] += 0.06f * v[1]; p[TILT] += 0.03f * v[1] }
                else if (v[0] == 2f) p[PADDLE] += 0.5f * v[1] * (0.5f + 0.5f * wave(t, 1024f, 0f))
                // A small nod in your pauses.
                val nd = listenNod(t, o, S_NOD)
                p[HEAD_PITCH] += nd[0]; p[HEAD_ROLL] += play * nd[1]; eyeK *= 1f - nd[2]; p[TILT] += 0.02f * nd[3]
                turnBlink = g[4]
            }
            FaceState.THINKING -> {
                // A few taps, a pause to think, a few more.
                val gate = smooth(clamp(0.5f + 1.5f * wave(t, 184f, 0f), 0f, 1f))
                val tap = sw * (0.5f - 0.5f * wave(t, 1141f, (PI / 2).toFloat())).pow(2) * gate
                val g = looks(t, S_GAZE, 1.8f, 6f, 0.6f, 0.5f, 0.2f, 0.8f, 0.05f, 1.1f, o)
                p[ORB_Y] = PEBBLE[1] + 0.07f * tap
                p[PAW_LY] = 0.33f + 0.07f * tap; p[PAW_RY] = 0.33f + 0.07f * tap
                p[HEAD_PITCH] = -0.30f + 0.2f * g[3]
                p[HEAD_YAW] = 0.12f * g[2]
                p[HEAD_ROLL] = sw * 0.10f * wave(t, 98f, 0f)
                p[LOOK_X] = 0.3f + g[0] - 0.4f * g[2]; p[LOOK_Y] = -0.7f + g[1] - 0.4f * g[3]
                p[ORB_GLOW] = 0.95f + 0.2f * wave(t, 424f, 0f)
                // Now and then (variety): the pebble rolled between its paws, a look up, the pebble held nearer.
                val v = variant(t, o, S_THINK, 0.5f)
                if (v[0] == 0f) {
                    val r = 0.03f * v[1] * wave(t, 1536f, 0f)
                    p[PAW_LX] += r; p[PAW_RX] -= r
                } else if (v[0] == 1f) {
                    p[HEAD_PITCH] += 0.25f * v[1]; p[LOOK_Y] += 0.9f * v[1]
                } else if (v[0] == 2f) {
                    p[ORB_Y] += 0.05f * v[1]; p[PAW_LY] += 0.05f * v[1]; p[PAW_RY] += 0.05f * v[1]; p[HEAD_PITCH] -= 0.06f * v[1]
                }
                turnBlink = g[4]
            }
            FaceState.SPEAKING -> {
                // Holds the pebble and talks with its eyes and head, in phrases,
                // never on top of a look (CritterPose.mouthOf for the mouth).
                val g = looks(t, S_GAZE, 1.8f, 6f, 0.65f, 0.5f, 0.18f, 0f, 0.06f, 1.1f, o)
                // (With the host's phrase ends, the gestures land on them instead.)
                val b = if (o.phraseN >= 0) phraseBeat(t, o, S_PHRASE, S_GAZE, 1.8f, 6f, 0.65f) else beat(t, S_BEAT, S_GAZE, 1.8f, 6f, 0.65f)
                val x = b[1]
                ackK = if (b[0] >= 0f) 1f - bump(clamp(x / 1.6f, 0f, 1f)) else 1f
                p[SPEAK] = 1f
                p[TILT] = 0.16f
                p[HEAD_PITCH] = 0.05f
                p[HEAD_YAW] = sw * 0.05f * noise(t, N_YAW, 4f) + 0.08f * g[2]
                p[HEAD_ROLL] = sw * 0.04f * noise(t, N_ROLL, 4f)
                p[LOOK_X] = g[0] - 0.16f * g[2]; p[LOOK_Y] = g[1] - 0.16f * g[3]
                p[ORB_GLOW] = 0.6f + 0.45f * amp
                if (b[0] == 0f) {
                    p[HEAD_PITCH] -= hap * 0.06f * (bump(x / 0.7f) - 0.3f * bump((x - 0.55f) / 0.7f))
                } else if (b[0] == 1f) {
                    val e = hap * envAHR(x, 0.4f, 0.3f, 0.6f)
                    p[PAW_LY] += 0.06f * e; p[PAW_RY] += 0.06f * e; p[PAW_LZ] -= 0.05f * e; p[PAW_RZ] += 0.05f * e
                    p[HEAD_PITCH] -= hap * 0.025f * bump(x / 0.9f)
                } else if (b[0] == 2f) {
                    p[HEAD_ROLL] += hap * play * 0.07f * bump(x / 1.2f)
                }
                turnBlink = g[4]
            }
            FaceState.APPROVAL -> {
                // Head up, pebble held up a little toward you in both paws,
                // forearms along the chest (never a raised hand), still.
                val g = restingGaze(t, S_GAZE)
                p[TILT] = 0.20f
                p[HEAD_PITCH] = 0.12f
                p[PAW_LX] = -0.08f; p[PAW_RX] = -0.08f
                p[PAW_LZ] = -0.07f; p[PAW_RZ] = 0.07f
                p[PAW_LY] = 0.38f; p[PAW_RY] = 0.38f
                p[ORB_X] = -0.08f
                p[ORB_Y] = PEBBLE[1] + 0.07f
                p[EYE_L] = 1f + 0.1f * play; p[EYE_R] = p[EYE_L]
                p[LOOK_X] = g[0]; p[LOOK_Y] = g[1]
                p[ORB_GLOW] = 0.9f
                calm = 0.7f; blinkSlow = 1.4f
                // The small reaction as it arrives (variety), then still.
                val ar = arrivalOf(state, o, since)
                p[HEAD_PITCH] += ar[0]; p[HEAD_ROLL] += play * ar[1]; p[TILT] += ar[2] + 0.03f * ar[4]; eyeK *= 1f - ar[3]
            }
            FaceState.STANDBY -> {
                val e = happening(t, 16f, 0.5f, 5.5f, S_EVENT, 0.35f, 1)
                val sigh = if (e[0] == 0f) bump(e[1] / 4.5f) else 0f
                p[TILT] = 0.04f
                p[HEAD_PITCH] = 0.10f - 0.03f * sigh
                p[EYE_L] = 0f; p[EYE_R] = 0f
                p[ORB_GLOW] = 0.15f
                p[RIPPLE] = 0.005f
                deepBreath = sigh; calm = 0.4f
                breathK = 171f; breathDepth = 1.8f; blinks = false
                pawsOnEyes = true
            }
            FaceState.ERROR -> {
                // A still, concerned look, holding its pebble; nothing comic.
                val g = restingGaze(t, S_GAZE)
                p[HEAD_ROLL] = -0.15f * play
                p[HEAD_PITCH] = 0.02f
                p[EYE_L] = 0.8f; p[EYE_R] = 0.8f
                p[LOOK_X] = g[0]; p[LOOK_Y] = -0.25f + g[1]
                p[ORB_GLOW] = 0.35f
                calm = 0.8f; blinkSlow = 1.4f
                val ar = arrivalOf(state, o, since)
                p[HEAD_PITCH] += ar[0]; p[HEAD_ROLL] += play * ar[1]; p[TILT] += ar[2] + 0.03f * ar[4]; eyeK *= 1f - ar[3]
            }
            FaceState.BANKED -> {
                val e = happening(t, 16f, 0.5f, 5.5f, S_EVENT, 0.55f, 1)
                val x = e[1]
                val droop = if (e[0] == 0f) {
                    if (x < 3.2f) smooth(clamp(x / 3.2f, 0f, 1f)) else 1f - smooth(clamp((x - 3.2f) / 0.8f, 0f, 1f))
                } else 0f
                p[EYE_L] = 0.35f * (1f - 0.7f * droop); p[EYE_R] = p[EYE_L]
                p[HEAD_PITCH] = -0.10f - 0.12f * droop
                p[ORB_GLOW] = 0.25f
                calm = 0.8f
                breathK = 205f; blinkSlow = 2.5f
            }
            FaceState.IDLE -> {
                // Floats, looks about, and now and then one small thing.
                val g = looks(t, S_GAZE, 1.5f, 6f, 0.35f, 0.8f, 0.25f, 0f, 0.08f, 1.1f, o)
                val ev = evI
                val x = ev[1]
                var hx = g[2]
                p[TILT] = 0.10f + sw * 0.011f * shift(t, S_ROLL)
                p[ROCK] = sw * 0.01f * shift(t, S_LEAN)
                p[PAW_LY] += sw * 0.008f * wave(t, 150f, 0f); p[PAW_RY] += sw * 0.008f * wave(t, 150f, 2.0f)
                if (ev[0] == 0f) {
                    // Washes its face.
                    wash = hap * envAHR(x, 0.6f, 2.2f, 0.8f)
                    p[HEAD_PITCH] += 0.1f * wash
                    eyeK = 1f - 0.6f * wash
                } else if (ev[0] == 1f || ev[0] == 2f) {
                    // Rolls lazily to one side and looks that way (a small roll).
                    val s = if (ev[0] == 1f) -1f else 1f
                    val e = hap * envAHR(x, 1.4f, 1.8f, 1.8f)
                    p[ROCK] += s * 0.02f * e
                    hx += (s * 0.6f - hx) * e
                } else if (ev[0] == 3f) {
                    // Kicks its feet a few times.
                    p[PADDLE] = hap * envAHR(x, 0.4f, 1.8f, 0.8f) * (0.5f + 0.5f * wave(t, 1024f, 0f))
                } else if (ev[0] == 4f) {
                    // Rubs its pebble.
                    val e = hap * envAHR(x, 0.5f, 1.5f, 0.8f)
                    val r = 0.03f * wave(t, 1536f, 0f) * e
                    p[ORB_Y] += 0.03f * e; p[PAW_LY] += 0.03f * e; p[PAW_RY] += 0.03f * e
                    p[PAW_LX] += r; p[PAW_RX] -= r
                }
                p[HEAD_YAW] = 0.25f * hx
                p[HEAD_PITCH] += 0.10f * g[3]
                p[HEAD_ROLL] = sw * 0.05f * wave(t, 67f, 0f)
                p[LOOK_X] = g[0] - 0.4f * hx; p[LOOK_Y] = g[1] - 0.4f * g[3]
                turnBlink = g[4]
                if (fw > 0f) {
                    // Working beside you: it looks at the pebble on its chest, far fewer looks.
                    val f = gaze(t, S_FOCUS, 4f, 12f, 0.75f, 0.3f, 0.12f, 0f, 0.03f, 1.6f)
                    p[HEAD_YAW] += (0.2f * f[2] - p[HEAD_YAW]) * fp
                    p[HEAD_PITCH] += (-0.22f + 0.1f * f[3] - p[HEAD_PITCH]) * fp
                    p[LOOK_X] += (0.3f + f[0] - 0.4f * f[2] - p[LOOK_X]) * fp
                    p[LOOK_Y] += (-0.6f + f[1] - 0.4f * f[3] - p[LOOK_Y]) * fp
                    turnBlink *= 1f - fp
                }
                // The small stretch in the water as a focus session ends.
                if (fe > 0f) { stretch(p, fe); eyeK *= 1f - 0.4f * fe; deepBreath = max(deepBreath, fe) }
                if (cw > 0f && cu[0] == 0f) {
                    // Cute moment: it rolls right over in the water (under calm, only a small roll and back).
                    val x = cu[1]
                    p[ROCK] += fullTurn(x, 0.8f, 4.8f, CUTE_LEN[0], cw) +
                        0.25f * cw * (1f - smooth(clamp((cw - 0.8f) / 0.2f, 0f, 1f))) * bump((x - 0.8f) / 4.8f)
                    eyeK *= 1f - cw * envAHR(x - 2.0f, 0.5f, 1.6f, 0.6f)
                    p[RIPPLE] += 0.008f * cw * bump((x - 1.0f) / 5.5f)
                    turnBlink *= 1f - cw * envAHR(x, 0.6f, 5.4f, 0.8f)
                } else if (cw > 0f && cu[0] == 1f) {
                    // Cute moment: it juggles its pebble from paw to paw over its chest, eyes following.
                    val x = cu[1]
                    val j = cw * envAHR(x, 0.8f, 4.6f, 1.0f)
                    val s = sin(TAU * 0.55f * (x - 0.8f))
                    val c = 1f - s * s
                    p[ORB_Z] += 0.10f * j * s; p[ORB_Y] += j * (0.03f + 0.09f * c)
                    p[PAW_LZ] += (-0.13f - p[PAW_LZ]) * j; p[PAW_RZ] += (0.13f - p[PAW_RZ]) * j
                    p[PAW_LY] += j * (0.03f + 0.05f * max(0f, -s)); p[PAW_RY] += j * (0.03f + 0.05f * max(0f, s))
                    p[LOOK_Y] += (-0.3f - 0.4f * s - p[LOOK_Y]) * j; p[LOOK_X] += (0.2f - p[LOOK_X]) * j
                    p[HEAD_PITCH] += (-0.12f - p[HEAD_PITCH]) * j
                    turnBlink *= 1f - j
                }
            }
        }

        // Stroked: it rolls a little toward your hand, leans its head in, a happy kick.
        if (pw > 0f) {
            p[ROCK] += 0.05f * pw * o.petX
            p[HEAD_ROLL] += pw * play * (0.10f * o.petX + 0.03f * o.petDir)
            p[HEAD_PITCH] += 0.03f * pw
            p[PADDLE] += 0.3f * pw * (0.5f + 0.5f * wave(t, 700f, 0f))
            eyeK *= 1f - 0.5f * pw
        }
        // A fact saved: one small nod, its head end lifting a touch. A long answer ready: the pebble glows up once.
        val an = if (awake(state)) ackNodOf(t, o) else ZERO2
        p[HEAD_PITCH] += ackK * an[0]; p[TILT] += 0.02f * ackK * an[1]
        val gl = if (awake(state)) ackGlowOf(t, o) else 0f
        p[ORB_GLOW] += 0.4f * gl; p[ORB_R] *= 1f + 0.12f * gl

        // Floating: the whole otter bobs and rocks with the water, gently.
        val settle = (1f - 0.5f * o.calm) * (1f - 0.6f * o.serious) * (1f - o.still)
        val water = calm * settle
        // The small waves and rings on the water (seaotter.sksl's waterSlope)
        // quieten with the options too - calm halves them, still stops them.
        // (Only the options: each state already sets its own ripple.)
        p[RIPPLE] *= settle
        p[BOB] = 0.009f * water * wave(t, 179f, 0f)
        p[ROCK] += 0.025f * water * wave(t, 130f, 0.6f)
        val b = breathWave(t, breathK, N_BREATH) * (1f + 0.6f * deepBreath)
        p[BREATH] = 1f + 0.02f * breathDepth * b

        val w = if (state == FaceState.STANDBY) 0f else clamp(look.w, 0f, 1f)
        if (w > 0f) {
            val lx = clamp(look.x, -1f, 1f)
            val ly = clamp(look.y, -1f, 1f)
            p[LOOK_X] += (lx - p[LOOK_X]) * w
            p[LOOK_Y] += (ly - p[LOOK_Y]) * w
            p[HEAD_YAW] += o.head * 0.2f * lx * w
            p[HEAD_PITCH] += o.head * 0.2f * ly * w
        }

        // Paws that go to the head are placed after the head has turned; while
        // they are away the pebble rests on its chest.
        if (pawsOnEyes) {
            setPaw(p, PAW_LX, onHead(p, -0.10f, 0.05f, -0.25f))
            setPaw(p, PAW_RX, onHead(p, 0.10f, 0.05f, -0.25f))
            p[ORB_Y] = PEBBLE_DOWN
        }
        if (wash > 0f) {
            // Both paws to the near side of its face, held out where they show.
            val r = 0.03f * wave(t, 1229f, 0f)
            val l = onHead(p, 0.22f, -0.15f + r, -0.21f)
            val rr = onHead(p, 0.27f, -0.04f + r, -0.15f)
            p[PAW_LX] += (l[0] - p[PAW_LX]) * wash; p[PAW_LY] += (l[1] - p[PAW_LY]) * wash; p[PAW_LZ] += (l[2] - p[PAW_LZ]) * wash
            p[PAW_RX] += (rr[0] - p[PAW_RX]) * wash; p[PAW_RY] += (rr[1] - p[PAW_RY]) * wash; p[PAW_RZ] += (rr[2] - p[PAW_RZ]) * wash
            p[ORB_Y] += (PEBBLE_DOWN - p[ORB_Y]) * wash
        }
        farewell(p, state, o)

        CritterPose.lidSet(p, LID, state)
        val q = 1f - o.quiet
        val k = eyeK * (1f - q * max(if (blinks) blinkAt(t, S_BLINK, blinkSlow, 2f, 10f) else 0f, turnBlink))
        p[EYE_L] *= k
        p[EYE_R] *= k
        return p
    }

    /**
     * Hello and goodbye - the desktop's otter farewell(): a little wave of
     * its paw (nothing asleep or dozing; none of it waiting on you or at an
     * error - [CritterPose.switchE]), then it dives under the water; hello,
     * it pops back up with a splash of rings, a small bob past the surface,
     * and looks at you.
     */
    private const val DIVE = 0.6f
    private fun farewell(p: FloatArray, state: FaceState, o: Opts) {
        val g = o.goodbye
        val h = o.hello
        if (g <= 0f && h >= 1f) return
        val e = switchE(o, state)
        val aw = if (awake(state)) 1f else 0f
        if (g > 0f) {
            val a = e * bump(clamp(g / 0.6f, 0f, 1f))
            val at = e * aw * ease(g / 0.2f)
            p[LOOK_X] += (0f - p[LOOK_X]) * at; p[LOOK_Y] += (0f - p[LOOK_Y]) * at
            p[HEAD_YAW] += (0f - p[HEAD_YAW]) * at
            val wv = a * aw
            p[PAW_RX] -= 0.16f * wv; p[PAW_RY] += 0.20f * wv; p[PAW_RZ] += 0.10f * wv + 0.05f * wv * sin(TAU * 1.6f * g)
            val d = e * ease((g - 0.4f) / 0.6f)
            p[BOB] -= DIVE * d; p[TILT] -= 0.2f * d
            p[RIPPLE] += 0.01f * e * bump((g - 0.45f) / 0.55f)
        }
        if (h < 1f) {
            val d = e * (1f - ease(h / 0.45f))
            p[BOB] -= DIVE * d - e * 0.035f * bump((h - 0.3f) / 0.45f); p[TILT] -= 0.2f * d
            p[RIPPLE] += 0.012f * e * bump((h - 0.1f) / 0.8f)
            val at = e * aw * ease((h - 0.25f) / 0.25f) * (1f - ease((h - 0.8f) / 0.2f))
            p[LOOK_X] += (0f - p[LOOK_X]) * at; p[LOOK_Y] += (0f - p[LOOK_Y]) * at
            p[HEAD_YAW] += (0f - p[HEAD_YAW]) * at
        }
    }

    /** A small stretch in the water, [s] 0..1: paws up and apart, chin up, toes out. */
    private fun stretch(p: FloatArray, s: Float) {
        p[PAW_LY] += 0.06f * s; p[PAW_RY] += 0.06f * s; p[PAW_LZ] -= 0.06f * s; p[PAW_RZ] += 0.06f * s
        p[HEAD_PITCH] += 0.10f * s; p[TILT] += 0.04f * s; p[PADDLE] += 0.5f * s
    }

    /** The otter's waking up and nodding off - the desktop's wakeSleep in critter-otter.js, and its notes. */
    private fun wakeSleep(p: FloatArray, state: FaceState, x: Float, k: Float, ex: Float, t: Float, f: FloatArray?) {
        val e = ex * k
        if (state == FaceState.STANDBY && f != null) {
            // Nodding off: a slow stretch, then its paws come up over its eyes
            // (leaving the pebble on its chest) and it settles.
            val s = e * envAHR(x - 0.15f, 0.5f, 0.25f, 0.5f)
            val lids = (1f - 0.35f * ease((x - 0.2f) / 0.8f)) * (1f - 0.5f * ex * envAHR(x - 0.15f, 0.5f, 0.25f, 0.5f)) *
                (1f - ease((x - 1.4f) / 0.8f))
            val lid = k * toward(eyesClose(x), lids, ex)
            p[EYE_L] = f[EYE_L] * lid; p[EYE_R] = f[EYE_R] * lid
            CritterPose.lidNod(p, f, LID, 1f - lid)   // the painted lid comes down as the eyes close
            // Its paws (and the pebble) stay where they were until 1.2 s.
            val hold = e * (1f - ease((x - 1.2f) / 1.2f))
            for (i in PAW_LX..PAW_RZ) p[i] = toward(p[i], f[i], hold)
            p[ORB_X] = toward(p[ORB_X], f[ORB_X], hold); p[ORB_Y] = toward(p[ORB_Y], f[ORB_Y], hold)
            stretch(p, s)
            return
        }
        // Waking: paws over its eyes a moment, rubbing them, then away into a
        // small stretch and back to the pebble, picking it up.
        val s = e * envAHR(x - 1.0f, 0.4f, 0.3f, 0.4f)
        stretch(p, s)
        val face = e * (1f - ease((x - 1.0f) / 1.0f))
        if (face > 0f) {
            val rub = envAHR(x - 0.3f, 0.2f, 0.45f, 0.2f)
            val ph = TAU * 2f * (x - 0.3f)
            val l = onHead(p, -0.10f, 0.05f - 0.05f * rub + 0.025f * rub * sin(ph), -0.25f)
            val r = onHead(p, 0.10f, 0.05f - 0.05f * rub - 0.025f * rub * sin(ph), -0.25f)
            for (i in 0 until 3) {
                p[PAW_LX + i] = toward(p[PAW_LX + i], l[i], face)
                p[PAW_RX + i] = toward(p[PAW_RX + i], r[i], face)
            }
        }
        p[ORB_Y] = toward(p[ORB_Y], PEBBLE_DOWN, e * (1f - ease((x - 1.6f) / 0.6f)))
        val lids = 0.4f * ease((x - 0.45f) / 0.4f) + 0.6f * ease((x - 1.05f) / 0.45f)
        val fe = 1f - k * (1f - toward(eyesOpen(x), lids, ex))
        p[EYE_L] *= fe; p[EYE_R] *= fe
        CritterPose.lidWake(p, LID, x, k)   // ...and lifts a little after they open
    }

    internal val HALF = CritterPose.halfLives(
        N,
        intArrayOf(EYE_L, EYE_R, LOOK_X, LOOK_Y), intArrayOf(SPEAK), intArrayOf(HEAD_YAW, HEAD_PITCH, HEAD_ROLL),
        intArrayOf(PAW_LX, PAW_LY, PAW_LZ, PAW_RX, PAW_RY, PAW_RZ, ORB_X, ORB_Y, ORB_Z), intArrayOf(PADDLE), LID,
    ).also { h ->
        // (rock is an angle: rolled right over, it settles the short way round.)
        h.cut[ROCK] = PI.toFloat()
    }

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

    private const val WATER_Y = -0.42f

    /** Uniform name to value; [mouth] as for [CritterPose.uniforms]. */
    fun uniforms(p: FloatArray, mouth: FloatArray? = null): Map<String, FloatArray> {
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
            "uFace" to floatArrayOf(clamp(p[EYE_L], 0f, 1.2f), clamp(p[EYE_R], 0f, 1.2f), clamp(p[PADDLE], 0f, 1f)),
            "uLid" to floatArrayOf(clamp(p[LID], 0f, 1f), clamp(p[LID_SLOPE], -1f, 1f)),
            "uMouth" to CritterPose.mouthOf(p[SPEAK], mouth),
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

    // The otter's camera (seaotter.sksl): target x, y, z, distance, pitch.
    private val CAM = floatArrayOf(0f, -0.30f, 0f, 3.30f, 0.50f)

    /** Where its sleeping Zs rise from: [asleep, x, y] - see [CritterPose.overlay]. */
    fun overlay(p: FloatArray, yaw: Float = 0f, pitch: Float = 0f, zoom: Float = 1f): FloatArray {
        val bm = mul(rz(-p[TILT]), rx(p[ROCK]))
        val h = onHead(p, -0.05f, 0.36f, 0.05f)
        val v = apply(bm, h[0], h[1], h[2])
        return CritterPose.overlayAt(p[ASLEEP], floatArrayOf(0.02f + v[0], WATER_Y + 0.02f + p[BOB] + v[1], v[2]), CAM, yaw, pitch, zoom)
    }
}
