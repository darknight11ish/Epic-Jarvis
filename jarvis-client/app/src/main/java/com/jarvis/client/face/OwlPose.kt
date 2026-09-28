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
import com.jarvis.client.face.CritterPose.gaze
import com.jarvis.client.face.CritterPose.listenNod
import com.jarvis.client.face.CritterPose.petOf
import com.jarvis.client.face.CritterPose.phraseBeat
import com.jarvis.client.face.CritterPose.variant
import kotlin.math.PI
import kotlin.math.cos
import kotlin.math.max
import kotlin.math.round
import kotlin.math.sin
import kotlin.math.sqrt

/**
 * The pygmy owl's body language - a line-for-line copy of the desktop's
 * `jarvis-desktop/src/critter-owl.js`, held to the same answers by
 * `critter-pose-golden.json` and `CritterPoseTest`, exactly as [CritterPose]
 * (the panda) is. Change one, change the other, re-run tools/gen_critters.py.
 *
 * Owls have no hands, so the orb floats beside it; the head does the talking
 * and the looking.
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
    private const val SPEAK = 10
    private const val LOOK_X = 11
    private const val LOOK_Y = 12
    private const val WING_L = 13
    private const val WING_R = 14
    private const val ORB_A = 15
    private const val ORB_Y = 16
    private const val ORB_D = 17
    private const val ORB_R = 18
    private const val ORB_GLOW = 19
    private const val LEAN = 20
    private const val BODY_ROLL = 21
    private const val ASLEEP = 22
    private const val N = 23

    // The orb is placed round the owl (the desktop's note): its angle round
    // the head's upright axis, its height and its distance from that axis.
    private const val ORB_AXIS_Z = -0.05f
    // Settling round the head, the orb never crosses this angle (just to the
    // viewer's left of straight in front of the face): it goes round the back.
    private const val ORB_CUT = (PI / 2 + 0.3).toFloat()
    private val ORB_REST = floatArrayOf(0.4636476f, 0.30f, 0.559017f, 0.09f)
    private val ORB_LISTEN = floatArrayOf(0.6947382f, 0.45f, 0.5467175f)
    private val ORB_SLEEP = floatArrayOf(0.1122027f, -0.02f, 0.6239391f)

    // The owl's own dice.
    private const val S_GAZE = 80
    private const val S_EVENT = 96
    private const val S_ROLL = 104
    private const val S_LEAN = 112
    private const val S_BEAT = 120
    private const val S_BLINK = 128
    // ...and for the new behaviours (critter-pose.js's note).
    private const val S_LISTEN = 136
    private const val S_THINK = 139
    private const val S_FOCUS = 142
    private const val S_NOD = 154
    private const val S_PHRASE = 155
    private const val S_CUTE = 156
    /** How long each cute moment lasts: turning its head right round, a hop. */
    private val CUTE_LEN = floatArrayOf(8.2f, 3.0f)

    // Its idle happenings, and how often each comes up (the desktop's EVENTS):
    // ruffle, wing left, wing right, tilt left, tilt right, slow blink.
    private val EVENTS = floatArrayOf(14f, 12f, 12f, 20f, 20f, 22f)

    /** Whether one of its idle happenings is playing at clock [t] - the desktop's busy(state, t). */
    fun busy(state: FaceState, t: Float, since: Float? = null, opts: Opts? = null): Boolean =
        state == FaceState.IDLE && (CritterPose.playing(happening(t, 16f, 0.5f, 5.5f, S_EVENT, 0.7f, EVENTS)) ||
            cuteBusy(t, since, opts, S_CUTE, CUTE_LEN))

    /** Whether one of its own talking gestures is playing at clock [t] - the desktop's gesturing(t). */
    fun gesturing(t: Float): Boolean {
        val b = beat(t, S_BEAT, S_GAZE, 1.8f, 6f, 0.65f)
        return b[0] >= 0f && b[1] >= 0f && b[1] < CritterPose.GESTURE_S
    }

    // Thinking: the orb circles the head, riding high in front, and comes up
    // the right-hand side first - the desktop's orbit() and its note.
    private const val ORBIT_K = 147f
    private const val ORBIT_R = 0.6f
    private const val ORB_SIDE = -0.3f
    private const val ORB_RISE_S = 0.8f
    private const val ORB_JOIN_S = 4.0f
    private const val ORBIT_W = CritterPose.TAU_F * ORBIT_K / CritterPose.LOOP
    private fun orbit(t: Float, since: Float, u: Float): FloatArray {
        val s = max(0f, since)
        val tc = t - s
        // Taken so that halfway through joining it is the short way round.
        val half = ORBIT_W * ORB_JOIN_S / 2f
        var d = CritterPose.phaseOf(tc, ORBIT_K) - ORB_SIDE + half
        d = d - CritterPose.TAU_F * round(d / CritterPose.TAU_F) - half
        // It waits at the side while it rises, then eases round to meet the
        // circle - and once it has, the circle itself (the desktop's note).
        val f = if (s >= ORB_JOIN_S) CritterPose.phaseOf(t, ORBIT_K)
        else ORB_SIDE + (d + ORBIT_W * s) * CritterPose.ease(s / ORB_JOIN_S)
        val ca = cos(f)
        val sa = sin(f)
        val r = 0.25f + (ORBIT_R - 0.25f) * u
        val y = 1.60f + (1.20f - 1.60f) * u + (0.03f + 0.13f * u) * sa
        val rise = CritterPose.ease(since / ORB_RISE_S)
        return floatArrayOf(f, 0.55f + (y - 0.55f) * rise, r, ca, sa)
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
        val hap = o.hap * (1f - fw) * (1f - cw * (if (cu[0] >= 0f) cuteQuiet(cu[1], CUTE_LEN[cu[0].toInt()]) else 0f)) * (1f - fe) * (1f - pw)
        val sw = o.sway
        val play = o.play
        val p = FloatArray(N)
        p[BREATH] = 1f; p[FLUFF] = 1f; p[EYE_L] = 1f; p[EYE_R] = 1f
        p[ORB_A] = ORB_REST[0]; p[ORB_Y] = ORB_REST[1] + sw * 0.03f * wave(t, 228f, 0f); p[ORB_D] = ORB_REST[2]
        p[ORB_R] = ORB_REST[3]; p[ORB_GLOW] = 0.55f
        p[ASLEEP] = if (state == FaceState.STANDBY) 1f else 0f
        // 284 cycles a loop: a breath every 3.6 seconds.
        var breathK = 284f
        var breathDepth = 1f
        var blinkSlow = 1.2f
        var blinks = true
        var turnBlink = 0f
        var eyeK = 1f
        var deepBreath = 0f
        var ackK = 1f
        var hop = 0f

        when (state) {
            FaceState.LISTENING -> {
                // Brows level: the shader's V grows sterner as `brow` rises.
                val g = looks(t, S_GAZE, 2f, 7f, 0.8f, 0.2f, 0.1f, 0f, 0.04f, 0.6f, o)
                p[HEAD_ROLL] = play * 0.34f + sw * 0.025f * wave(t, 188f, 0f)
                p[HEAD_PITCH] = 0.05f
                p[HEAD_YAW] = 0.15f * g[2]
                p[LEAN] = 0.04f
                p[EYE_L] = 1f + 0.12f * play; p[EYE_R] = p[EYE_L]
                p[BROW] = 0.1f
                p[FLUFF] = 1.02f
                p[LOOK_X] = g[0] - 0.7f * g[2]; p[LOOK_Y] = 0.1f + g[1]
                p[ORB_A] = ORB_LISTEN[0]; p[ORB_Y] = ORB_LISTEN[1]; p[ORB_D] = ORB_LISTEN[2]
                p[ORB_GLOW] = 0.55f + 0.5f * amp
                // Now and then (variety): the other tilt, leaning closer, a bob of the head.
                val v = variant(t, o, S_LISTEN, 0.4f)
                if (v[0] == 0f) p[HEAD_ROLL] -= 0.51f * play * v[1]
                else if (v[0] == 1f) { p[LEAN] += 0.03f * v[1]; p[FLUFF] -= 0.015f * v[1] }
                else if (v[0] == 2f) p[NECK_DROP] += 0.015f * v[1] * wave(t, 1024f, 0f)
                // A small nod in your pauses (a fluff for the ear flick).
                val nd = listenNod(t, o, S_NOD)
                p[HEAD_PITCH] += nd[0]; p[HEAD_ROLL] += play * nd[1]; eyeK *= 1f - nd[2]; p[FLUFF] += 0.03f * nd[3]
                turnBlink = g[4]
            }
            FaceState.THINKING -> {
                val q = orbit(t, since, sw)
                val ca = q[3]
                val sa = q[4]
                p[ORB_A] = q[0]; p[ORB_Y] = q[1]; p[ORB_D] = q[2]
                p[ORB_R] = 0.10f
                p[HEAD_ROLL] = sw * 0.26f * wave(t, 90f, 0f)
                p[HEAD_YAW] = o.head * 0.45f * ca * max(0f, sa) * smooth(clamp(sa / 0.3f, 0f, 1f))
                p[HEAD_PITCH] = 0.14f
                p[LOOK_X] = (0.35f + 0.55f * sw) * ca; p[LOOK_Y] = 0.45f - 0.1f * sw
                p[BROW] = 0.1f
                p[ORB_GLOW] = 0.95f + 0.2f * wave(t, 424f, 0f)
                // Now and then (variety): the other tilt, eyes narrowing, a bob of the head.
                val v = variant(t, o, S_THINK, 0.5f)
                if (v[0] == 0f) p[HEAD_ROLL] -= 0.15f * play * v[1]
                else if (v[0] == 1f) { eyeK *= 1f - 0.25f * v[1]; p[LEAN] += 0.025f * v[1] }
                else if (v[0] == 2f) p[NECK_DROP] += 0.015f * v[1] * wave(t, 1024f, 0f)
            }
            FaceState.SPEAKING -> {
                // The beak follows the mouth track (CritterPose.mouthOf); gestures in
                // phrases, never on top of a look; the eyes lead each look.
                val g = looks(t, S_GAZE, 1.8f, 6f, 0.65f, 0.5f, 0.18f, 0f, 0.04f, 0.6f, o)
                // (With the host's phrase ends, the gestures land on them instead.)
                val b = if (o.phraseN >= 0) phraseBeat(t, o, S_PHRASE, S_GAZE, 1.8f, 6f, 0.65f) else beat(t, S_BEAT, S_GAZE, 1.8f, 6f, 0.65f)
                val x = b[1]
                ackK = if (b[0] >= 0f) 1f - bump(clamp(x / 1.6f, 0f, 1f)) else 1f
                p[SPEAK] = 1f
                p[LEAN] = 0.04f
                p[HEAD_PITCH] = 0.03f
                p[HEAD_YAW] = sw * 0.06f * wave(t, 111f, 0f) + 0.12f * g[2]
                p[HEAD_ROLL] = sw * 0.035f * wave(t, 93f, 0.5f)
                p[LOOK_X] = g[0] - 0.28f * g[2]; p[LOOK_Y] = g[1] - 0.28f * g[3]
                p[BROW] = 0.1f + 0.1f * amp
                p[ORB_GLOW] = 0.6f + 0.45f * amp
                if (b[0] == 0f) {
                    p[HEAD_PITCH] -= hap * 0.07f * (bump(x / 0.7f) - 0.3f * bump((x - 0.55f) / 0.7f))
                    p[BROW] += hap * 0.15f * bump(x / 0.7f)
                } else if (b[0] == 1f) {
                    p[WING_R] += hap * 0.22f * envAHR(x, 0.4f, 0.3f, 0.6f)
                    p[HEAD_PITCH] -= hap * 0.025f * bump(x / 0.9f)
                } else if (b[0] == 2f) {
                    p[HEAD_ROLL] += hap * play * 0.08f * bump(x / 1.2f)
                }
                turnBlink = g[4]
            }
            FaceState.APPROVAL -> {
                // Drawn up, sleek and still, looking at you, brows level; no wave.
                val g = restingGaze(t, S_GAZE)
                p[NECK_DROP] = -0.02f
                p[FLUFF] = 0.98f
                p[LEAN] = 0.04f
                p[HEAD_PITCH] = 0.04f
                p[EYE_L] = 1f + 0.05f * play; p[EYE_R] = p[EYE_L]
                p[BROW] = 0.1f
                p[LOOK_X] = g[0]; p[LOOK_Y] = g[1]
                p[ORB_GLOW] = 0.9f
                blinkSlow = 1.6f
                // The small reaction as it arrives (variety), then still.
                val ar = arrivalOf(state, o, since)
                p[HEAD_PITCH] += ar[0]; p[HEAD_ROLL] += play * ar[1]; p[LEAN] += ar[2]; eyeK *= 1f - ar[3]
                p[FLUFF] -= 0.03f * ar[4]
            }
            FaceState.STANDBY -> {
                val e = happening(t, 16f, 0.5f, 5.5f, S_EVENT, 0.35f, 1)
                val sigh = if (e[0] == 0f) bump(e[1] / 4.5f) else 0f
                p[EYE_L] = 0f; p[EYE_R] = 0f
                p[FLUFF] = 1.10f
                p[NECK_DROP] = 0.08f + 0.015f * sigh
                p[HEAD_PITCH] = -0.18f - 0.03f * sigh
                p[HEAD_ROLL] = 0.10f * play
                p[ORB_A] = ORB_SLEEP[0]; p[ORB_Y] = ORB_SLEEP[1]; p[ORB_D] = ORB_SLEEP[2]
                p[ORB_GLOW] = 0.15f
                deepBreath = sigh
                breathK = 186f; breathDepth = 1.8f; blinks = false
            }
            FaceState.ERROR -> {
                // A still, concerned look: the brows' V flattened (worried, not stern).
                val g = restingGaze(t, S_GAZE)
                p[HEAD_ROLL] = -0.15f * play
                p[HEAD_PITCH] = -0.08f
                p[EYE_L] = 0.8f; p[EYE_R] = 0.8f
                p[BROW] = -1.5f
                p[LOOK_X] = g[0]; p[LOOK_Y] = -0.25f + g[1]
                p[FLUFF] = 1.03f
                p[ORB_GLOW] = 0.35f
                blinkSlow = 1.6f
                val ar = arrivalOf(state, o, since)
                p[HEAD_PITCH] += ar[0]; p[HEAD_ROLL] += play * ar[1]; p[LEAN] += ar[2]; eyeK *= 1f - ar[3]
                p[FLUFF] -= 0.03f * ar[4]
            }
            FaceState.BANKED -> {
                val e = happening(t, 16f, 0.5f, 5.5f, S_EVENT, 0.55f, 1)
                val x = e[1]
                val droop = if (e[0] == 0f) {
                    if (x < 3.2f) smooth(clamp(x / 3.2f, 0f, 1f)) else 1f - smooth(clamp((x - 3.2f) / 0.8f, 0f, 1f))
                } else 0f
                p[EYE_L] = 0.35f * (1f - 0.7f * droop); p[EYE_R] = p[EYE_L]
                p[HEAD_PITCH] = -0.12f - 0.12f * droop
                p[NECK_DROP] = 0.03f * droop
                p[FLUFF] = 1.05f
                p[LOOK_Y] = -0.2f
                p[ORB_GLOW] = 0.25f
                breathK = 205f; blinkSlow = 3f
            }
            FaceState.IDLE -> {
                // The head does the looking, and holds; now and then one small thing.
                val g = looks(t, S_GAZE, 1.5f, 6f, 0.35f, 0.7f, 0.25f, 0f, 0.04f, 0.8f, o)
                val ev = happening(t, 16f, 0.5f, 5.5f, S_EVENT, 0.7f, EVENTS)
                val x = ev[1]
                val roll = sw * 0.011f * shift(t, S_ROLL)
                p[BODY_ROLL] = roll
                p[LEAN] = sw * 0.011f * shift(t, S_LEAN)
                p[HEAD_YAW] = 0.40f * g[2]
                p[HEAD_PITCH] = 0.12f * g[3]
                p[HEAD_ROLL] = -0.5f * roll + sw * 0.04f * wave(t, 77f, 0.3f)
                p[LOOK_X] = g[0] - 0.8f * g[2]; p[LOOK_Y] = g[1] - 0.8f * g[3]
                p[FLUFF] = 1f + sw * 0.008f * wave(t, 61f, 0f)
                if (ev[0] == 0f) {
                    // A ruffle.
                    val e = hap * envAHR(x, 0.45f, 0.9f, 1.25f)
                    p[FLUFF] += 0.07f * e + hap * 0.012f * wave(t, 2048f, 0f) * bump((x - 0.4f) / 1.0f)
                    p[NECK_DROP] = 0.012f * e; p[HEAD_PITCH] -= 0.05f * e
                    eyeK = 1f - 0.3f * e
                } else if (ev[0] == 1f || ev[0] == 2f) {
                    // A wing lifted a little and folded back.
                    val s = if (ev[0] == 1f) -1f else 1f
                    val lift = hap * 0.42f * (bump(x / 1.1f) + 0.25f * bump((x - 0.8f) / 0.8f))
                    if (s < 0f) p[WING_L] += lift else p[WING_R] += lift
                    p[BODY_ROLL] += hap * s * 0.008f * bump(x / 1.6f)
                } else if (ev[0] == 3f || ev[0] == 4f) {
                    // A curious tilt of the head.
                    val s = if (ev[0] == 3f) -1f else 1f
                    p[HEAD_ROLL] += hap * s * 0.25f * envAHR(x, 0.5f, 1.6f, 0.9f)
                } else if (ev[0] == 5f) {
                    // A long slow blink (a blink, so the options leave it be -
                    // all but waking up's quiet, which has blinks of its own).
                    eyeK = 1f - 0.85f * envAHR(x, 0.45f, 0.35f, 0.6f) * (1f - o.quiet)
                }
                turnBlink = g[4]
                if (fw > 0f) {
                    // Working beside you: it half turns to watch the work, far fewer looks.
                    val f = gaze(t, S_FOCUS, 4f, 12f, 0.75f, 0.3f, 0.12f, 0f, 0.02f, 1.6f)
                    p[HEAD_YAW] += (0.35f + 0.4f * f[2] - p[HEAD_YAW]) * fp
                    p[HEAD_PITCH] += (-0.12f + 0.12f * f[3] - p[HEAD_PITCH]) * fp
                    p[LOOK_X] += (f[0] - 0.8f * f[2] - p[LOOK_X]) * fp
                    p[LOOK_Y] += (-0.2f + f[1] - 0.8f * f[3] - p[LOOK_Y]) * fp
                    turnBlink *= 1f - fp
                }
                // The small stretch as a focus session ends: a ruffle, wings eased out.
                if (fe > 0f) {
                    p[FLUFF] += 0.06f * fe; p[NECK_DROP] += 0.012f * fe; p[HEAD_PITCH] -= 0.05f * fe
                    p[WING_L] += 0.25f * fe; p[WING_R] += 0.25f * fe; eyeK *= 1f - 0.3f * fe
                    deepBreath = max(deepBreath, fe)
                }
                if (cw > 0f && cu[0] == 0f) {
                    // Cute moment: it turns its head right round (about 140 degrees), and back.
                    val s = if (CritterPose.hash01((kotlin.math.floor(cu[2]).toInt() and 4095) * 256 + S_CUTE + 1) < 0.5f) -1f else 1f
                    val x = cu[1]
                    val e = cw * (ease((x - 0.3f) / 3.6f) - ease((x - 4.5f) / 3.6f))
                    p[HEAD_YAW] += s * 2.4f * e
                    val hold = cw * envAHR(x, 0.8f, 6.6f, 0.8f)
                    p[LOOK_X] += (0f - p[LOOK_X]) * hold; p[LOOK_Y] += (0f - p[LOOK_Y]) * hold
                    p[HEAD_PITCH] += (0.05f - p[HEAD_PITCH]) * hold
                    turnBlink *= 1f - hold
                } else if (cw > 0f && cu[0] == 1f) {
                    // Cute moment: a little hop on its branch, and a look at you.
                    val x = cu[1]
                    hop = cw * (0.055f * bump((x - 0.55f) / 0.7f) - 0.012f * bump((x - 0.15f) / 0.5f) - 0.01f * bump((x - 1.1f) / 0.5f))
                    p[WING_L] += 0.3f * cw * bump((x - 0.5f) / 0.8f); p[WING_R] += 0.3f * cw * bump((x - 0.5f) / 0.8f)
                    p[FLUFF] += cw * (0.04f * bump((x - 1.05f) / 0.7f) - 0.02f * bump((x - 0.15f) / 0.5f))
                    p[NECK_DROP] += cw * 0.012f * bump((x - 0.15f) / 0.5f)
                    val at = cw * envAHR(x - 1.4f, 0.3f, 0.8f, 0.5f)
                    p[LOOK_X] += (0f - p[LOOK_X]) * at; p[LOOK_Y] += (0f - p[LOOK_Y]) * at
                    p[HEAD_YAW] += (0f - p[HEAD_YAW]) * at
                }
            }
        }

        // Stroked: it fluffs up and leans its head into your hand, eyes closing.
        if (pw > 0f) {
            p[HEAD_ROLL] += pw * play * (0.12f * o.petX + 0.03f * o.petDir)
            p[HEAD_PITCH] += 0.03f * pw
            p[NECK_DROP] -= 0.01f * pw
            p[FLUFF] += 0.05f * pw
            eyeK *= 1f - 0.6f * pw
        }
        // A fact saved: one small nod, a flick of its feathers. A long answer ready: the orb swells once.
        val an = if (awake(state)) ackNodOf(t, o) else ZERO2
        p[HEAD_PITCH] += ackK * an[0]; p[FLUFF] += 0.02f * ackK * an[1]
        val gl = if (awake(state)) ackGlowOf(t, o) else 0f
        p[ORB_GLOW] += 0.4f * gl; p[ORB_R] *= 1f + 0.2f * gl

        val b = wave(t, breathK, 0f) * (1f + 0.6f * deepBreath)
        p[BREATH] = 1f + 0.016f * breathDepth * b
        p[BOB] = 0.006f * breathDepth * b + hop

        val w = if (state == FaceState.STANDBY) 0f else clamp(look.w, 0f, 1f)
        if (w > 0f) {
            val lx = clamp(look.x, -1f, 1f)
            val ly = clamp(look.y, -1f, 1f)
            p[LOOK_X] += (lx - p[LOOK_X]) * w
            p[LOOK_Y] += (ly - p[LOOK_Y]) * w
            p[HEAD_YAW] += o.head * 0.3f * lx * w
            p[HEAD_PITCH] += o.head * 0.25f * ly * w
        }
        farewell(p, state, o)

        val q = 1f - o.quiet
        val k = eyeK * (1f - q * max(if (blinks) blinkAt(t, S_BLINK, blinkSlow, 3f, 12f) else 0f, turnBlink))
        p[EYE_L] *= k
        p[EYE_R] *= k
        return p
    }

    /**
     * Hello and goodbye - the desktop's owl farewell(): a small bow, then it
     * flies up out of the picture (its branch stays); hello, it flutters down
     * onto the branch with a fluff and looks at you. Waiting on you or at an
     * error: none of it, the host's cross-fade ([CritterPose.switchE]).
     */
    private const val RISE = 2.2f
    private fun farewell(p: FloatArray, state: FaceState, o: Opts) {
        val g = o.goodbye
        val h = o.hello
        if (g <= 0f && h >= 1f) return
        val e = switchE(o, state)
        val aw = if (awake(state)) 1f else 0f
        if (g > 0f) {
            val a = e * aw * bump(clamp(g / 0.6f, 0f, 1f))
            val at = e * aw * ease(g / 0.2f)
            p[LOOK_X] += (0f - p[LOOK_X]) * at; p[LOOK_Y] += (0f - p[LOOK_Y]) * at
            p[HEAD_YAW] += (0f - p[HEAD_YAW]) * at
            p[HEAD_PITCH] -= 0.25f * a; p[NECK_DROP] += 0.02f * a; p[LEAN] += 0.04f * a
            val up = e * ease((g - 0.35f) / 0.65f)
            p[WING_L] += 0.9f * e * ease((g - 0.3f) / 0.3f); p[WING_R] += 0.9f * e * ease((g - 0.3f) / 0.3f)
            p[BOB] += RISE * up
        }
        if (h < 1f) {
            p[BOB] += e * RISE * (1f - ease(h / 0.5f))
            p[BOB] -= e * 0.02f * bump((h - 0.42f) / 0.3f)
            val wg = e * 0.9f * (1f - ease((h - 0.4f) / 0.3f))
            p[WING_L] += wg; p[WING_R] += wg
            p[FLUFF] += e * 0.05f * bump((h - 0.42f) / 0.35f)
            val at = e * aw * ease((h - 0.3f) / 0.25f) * (1f - ease((h - 0.8f) / 0.2f))
            p[LOOK_X] += (0f - p[LOOK_X]) * at; p[LOOK_Y] += (0f - p[LOOK_Y]) * at
            p[HEAD_YAW] += (0f - p[HEAD_YAW]) * at
        }
    }

    /** The owl's waking up and nodding off - the desktop's wakeSleep in critter-owl.js, and its notes. */
    private fun wakeSleep(p: FloatArray, state: FaceState, x: Float, k: Float, ex: Float, t: Float, f: FloatArray?) {
        val e = ex * k
        if (state == FaceState.STANDBY && f != null) {
            // Nodding off: eyes half close, one last slow blink, then it fluffs
            // up round (a touch past, and settles) and tucks its head in.
            val lids = (1f - 0.5f * ease(x / 0.7f) - 0.5f * ease((x - 1.6f) / 0.7f)) * (1f - bump((x - 0.85f) / 0.65f))
            val lid = k * toward(eyesClose(x), lids, ex)
            p[EYE_L] = f[EYE_L] * lid; p[EYE_R] = f[EYE_R] * lid
            val head = e * (1f - ease((x - 1.6f) / 1.2f))
            p[NECK_DROP] = toward(p[NECK_DROP], f[NECK_DROP], head)
            p[HEAD_PITCH] = toward(p[HEAD_PITCH], f[HEAD_PITCH], head)
            p[HEAD_ROLL] = toward(p[HEAD_ROLL], f[HEAD_ROLL], head)
            p[FLUFF] = toward(p[FLUFF], f[FLUFF], e * (1f - ease((x - 1.4f) / 0.7f))) + 0.03f * e * bump((x - 1.7f) / 1.0f)
            return
        }
        // Waking: one eye opens, then the other; a quick ruffle with a small
        // shiver; its head draws up a little and settles with a small shake.
        val both = eyesOpen(x)
        val l = toward(both, 0.6f * ease((x - 0.15f) / 0.35f) + 0.4f * ease((x - 0.75f) / 0.3f), ex)
        val r = toward(both, ease((x - 0.55f) / 0.4f), ex)
        val fl = e * envAHR(x - 0.9f, 0.3f, 0.35f, 0.55f)
        p[EYE_L] *= (1f - k * (1f - l)) * (1f - 0.25f * fl)
        p[EYE_R] *= (1f - k * (1f - r)) * (1f - 0.25f * fl)
        p[FLUFF] += 0.06f * fl + 0.012f * e * wave(t, 2048f, 0f) * bump((x - 0.95f) / 0.9f)
        p[NECK_DROP] -= 0.015f * e * bump((x - 0.2f) / 1.3f)
        p[HEAD_ROLL] += 0.04f * e * (bump((x - 1.25f) / 0.45f) - bump((x - 1.6f) / 0.45f))
    }

    // The orb floats: it drifts to a new place more slowly than anything else,
    // and sideways faster than up and down (the desktop's note).
    internal val HALF = CritterPose.halfLives(
        N,
        intArrayOf(EYE_L, EYE_R, LOOK_X, LOOK_Y), intArrayOf(SPEAK), intArrayOf(HEAD_YAW, HEAD_PITCH, HEAD_ROLL, NECK_DROP, BROW),
        intArrayOf(), intArrayOf(WING_L, WING_R, FLUFF),
    ).also { h ->
        h.hl[ORB_A] = 0.16f; h.hl[ORB_Y] = 0.55f; h.hl[ORB_D] = 0.16f
        h.cut[ORB_A] = ORB_CUT
        for (i in intArrayOf(ORB_A, ORB_Y, ORB_D)) h.own[i] = true
    }

    /** How much this pose is speaking, 0..1 - what [uniforms] scales the beak by. */
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

    private const val SEAT_Y = -0.93f

    // The head as a keep-out egg (the desktop's clearOfHead).
    private val KEEP_C = floatArrayOf(0f, 0.30f, 0.0f)
    private val KEEP_R = floatArrayOf(0.49f, 0.42f, 0.46f)
    private const val KEEP_GAP = 0.03f
    private const val KEEP_SOFT = 0.03f

    /** The orb, eased out of the head if it would sink into it - see the desktop's note. */
    private fun clearOfHead(orb: FloatArray, r: Float, neck: FloatArray, hm: FloatArray): FloatArray {
        val rel = floatArrayOf(orb[0] - neck[0], orb[1] - neck[1], orb[2] - neck[2])
        val h = FloatArray(3) { i ->
            val row = invRow(hm, i)
            row[0] * rel[0] + row[1] * rel[1] + row[2] * rel[2] - KEEP_C[i]
        }
        val q0 = floatArrayOf(h[0] / KEEP_R[0], h[1] / KEEP_R[1], h[2] / KEEP_R[2])
        val q1 = floatArrayOf(q0[0] / KEEP_R[0], q0[1] / KEEP_R[1], q0[2] / KEEP_R[2])
        val k0 = sqrt(q0[0] * q0[0] + q0[1] * q0[1] + q0[2] * q0[2])
        val k1 = sqrt(q1[0] * q1[0] + q1[1] * q1[1] + q1[2] * q1[2])
        if (k1 < 1e-6f) return orb
        val gap = k0 * (k0 - 1f) / k1 - r
        val short = KEEP_GAP + KEEP_SOFT - gap
        if (short <= 0f) return orb
        val push = if (short < 2f * KEEP_SOFT) short * short / (4f * KEEP_SOFT) else short - KEEP_SOFT
        val n = apply(hm, q1[0] / k1, q1[1] / k1, q1[2] / k1)
        return floatArrayOf(orb[0] + n[0] * push, orb[1] + n[1] * push, orb[2] + n[2] * push)
    }

    /** Uniform name to value; [mouth] as for [CritterPose.uniforms]. */
    fun uniforms(p: FloatArray, mouth: FloatArray? = null): Map<String, FloatArray> {
        val bodyPos = floatArrayOf(0f, SEAT_Y + p[BOB], 0f)
        // Its weight shifts on the branch, about its feet.
        val bm = mul(rz(-p[BODY_ROLL]), rx(-p[LEAN]))
        fun toWorld(x: Float, y: Float, z: Float): FloatArray {
            val v = apply(bm, x, y, z)
            return floatArrayOf(bodyPos[0] + v[0], bodyPos[1] + v[1], bodyPos[2] + v[2])
        }
        val neck = toWorld(0f, 0.70f - p[NECK_DROP], -0.02f)
        val hm = mul(bm, mul(ry(-p[HEAD_YAW]), mul(rx(p[HEAD_PITCH]), rz(-p[HEAD_ROLL]))))
        fun wing(lift: Float, side: Float) = rz(side * clamp(lift, 0f, 1.6f))
        val wl = wing(p[WING_L], -1f)
        val wr = wing(p[WING_R], 1f)
        // The orb floats free: the owl's weight shifts do not carry it.
        val orb = clearOfHead(
            floatArrayOf(
                bodyPos[0] + p[ORB_D] * cos(p[ORB_A]), bodyPos[1] + p[ORB_Y], bodyPos[2] + ORB_AXIS_Z - p[ORB_D] * sin(p[ORB_A]),
            ),
            p[ORB_R], neck, hm,
        )
        return linkedMapOf(
            "uOrb" to floatArrayOf(orb[0], orb[1], orb[2], p[ORB_R]),
            "uBodyPos" to bodyPos,
            "uBodyR0" to invRow(bm, 0), "uBodyR1" to invRow(bm, 1), "uBodyR2" to invRow(bm, 2),
            "uBreath" to floatArrayOf(p[BREATH], p[FLUFF]),
            "uNeck" to neck,
            "uHeadR0" to invRow(hm, 0), "uHeadR1" to invRow(hm, 1), "uHeadR2" to invRow(hm, 2),
            "uWingL0" to invRow(wl, 0), "uWingL1" to invRow(wl, 1), "uWingL2" to invRow(wl, 2),
            "uWingR0" to invRow(wr, 0), "uWingR1" to invRow(wr, 1), "uWingR2" to invRow(wr, 2),
            "uFace" to floatArrayOf(clamp(p[EYE_L], 0f, 1.2f), clamp(p[EYE_R], 0f, 1.2f), p[BROW]),
            "uMouth" to CritterPose.mouthOf(p[SPEAK], mouth),
            "uLook" to floatArrayOf(clamp(p[LOOK_X], -1f, 1f), clamp(p[LOOK_Y], -1f, 1f)),
            "uOrbGlow" to floatArrayOf(clamp(p[ORB_GLOW], 0f, 1.5f)),
        )
    }

    // The owl's camera (pygmyowl.sksl): target x, y, z, distance, pitch.
    private val CAM = floatArrayOf(0f, -0.12f, 0f, 3.35f, 0f)

    /** Where its sleeping Zs rise from: [asleep, x, y] - see [CritterPose.overlay]. */
    fun overlay(p: FloatArray, yaw: Float = 0f, pitch: Float = 0f, zoom: Float = 1f): FloatArray {
        val by = SEAT_Y + p[BOB]
        val bm = mul(rz(-p[BODY_ROLL]), rx(-p[LEAN]))
        val nv = apply(bm, 0f, 0.70f - p[NECK_DROP], -0.02f)
        val hm = mul(bm, mul(ry(-p[HEAD_YAW]), mul(rx(p[HEAD_PITCH]), rz(-p[HEAD_ROLL]))))
        val hv = apply(hm, 0.30f, 0.80f, 0.02f)
        return CritterPose.overlayAt(p[ASLEEP], floatArrayOf(nv[0] + hv[0], by + nv[1] + hv[1], nv[2] + hv[2]), CAM, yaw, pitch, zoom)
    }
}
