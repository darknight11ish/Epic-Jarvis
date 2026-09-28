package com.jarvis.client.face

import com.jarvis.client.FaceState
import com.jarvis.client.face.CritterPose.Look
import com.jarvis.client.face.CritterPose.NONE
import com.jarvis.client.face.CritterPose.Opts
import com.jarvis.client.face.CritterPose.ZERO2
import com.jarvis.client.face.CritterPose.ackGlowOf
import com.jarvis.client.face.CritterPose.ackNodOf
import com.jarvis.client.face.CritterPose.apply
import com.jarvis.client.face.CritterPose.awake
import com.jarvis.client.face.CritterPose.blinkAt
import com.jarvis.client.face.CritterPose.bump
import com.jarvis.client.face.CritterPose.chain
import com.jarvis.client.face.CritterPose.clamp
import com.jarvis.client.face.CritterPose.cuteAt
import com.jarvis.client.face.CritterPose.cuteBusy
import com.jarvis.client.face.CritterPose.cuteOf
import com.jarvis.client.face.CritterPose.cuteQuiet
import com.jarvis.client.face.CritterPose.ease
import com.jarvis.client.face.CritterPose.envAHR
import com.jarvis.client.face.CritterPose.extras
import com.jarvis.client.face.CritterPose.eyesClose
import com.jarvis.client.face.CritterPose.focusEndOf
import com.jarvis.client.face.CritterPose.focusOf
import com.jarvis.client.face.CritterPose.gaze
import com.jarvis.client.face.CritterPose.happening
import com.jarvis.client.face.CritterPose.hash01
import com.jarvis.client.face.CritterPose.invRow
import com.jarvis.client.face.CritterPose.listenNod
import com.jarvis.client.face.CritterPose.looks
import com.jarvis.client.face.CritterPose.mul
import com.jarvis.client.face.CritterPose.petOf
import com.jarvis.client.face.CritterPose.phraseBeat
import com.jarvis.client.face.CritterPose.restingGaze
import com.jarvis.client.face.CritterPose.rx
import com.jarvis.client.face.CritterPose.ry
import com.jarvis.client.face.CritterPose.rz
import com.jarvis.client.face.CritterPose.shift
import com.jarvis.client.face.CritterPose.toward
import com.jarvis.client.face.CritterPose.variant
import com.jarvis.client.face.CritterPose.varOf
import com.jarvis.client.face.CritterPose.wave
import kotlin.math.PI
import kotlin.math.cos
import kotlin.math.floor
import kotlin.math.max
import kotlin.math.pow
import kotlin.math.sin
import kotlin.math.tanh

/**
 * The robot's body language - a line-for-line copy of the desktop's
 * `jarvis-desktop/src/critter-robot.js`, held to the same answers by
 * `critter-pose-golden.json` and `CritterPoseTest`.
 *
 * The owner's fifth face (2026-09-28): a small cute robot that floats, from
 * their own picture. It has no mouth and no orb: its glowing eyes on its
 * visor carry the state's colour and the expression, and pulse with the real
 * voice while it speaks. Now and then at rest it zips round inside its own
 * space, and its two cute moments take turns (a wave, polishing its visor).
 * It does every new behaviour the animals do, with the same options and
 * timing. The desktop's file says more about each piece.
 */
object RobotPose {

    private const val POS_X = 0
    private const val POS_Y = 1
    private const val POS_Z = 2
    private const val YAW = 3
    private const val ROLL = 4
    private const val PITCH = 5
    private const val HEAD_YAW = 6
    private const val HEAD_PITCH = 7
    private const val HEAD_ROLL = 8
    private const val EYE_L = 9
    private const val EYE_R = 10
    private const val HAPPY = 11
    private const val SIZE = 12
    private const val SQUINT = 13
    private const val SLANT = 14
    private const val LOOK_X = 15
    private const val LOOK_Y = 16
    private const val GLOW = 17
    private const val SPEAK = 18
    private const val FIN_L = 19
    private const val FIN_R = 20
    private const val FIN_GLOW = 21
    private const val GLEAM = 22
    private const val L_HX = 23
    private const val L_HY = 24
    private const val L_HZ = 25
    private const val R_HX = 26
    private const val R_HY = 27
    private const val R_HZ = 28
    private const val ASLEEP = 29
    private const val N = 30

    private const val TAU = (2.0 * PI).toFloat()
    private const val HALF_PI = (PI / 2).toFloat()

    // Where the middle of its body floats at rest, and where things are on it
    // (the body's frame) - the desktop's constants.
    private const val REST_Y = -0.37f
    private val NECK = floatArrayOf(0f, 0.285f, 0f)
    private const val HC_Y = 0.335f
    private val SH_L = floatArrayOf(-0.29f, 0.17f, 0f)
    private val SH_R = floatArrayOf(0.29f, 0.17f, 0f)
    private val HAND_L = floatArrayOf(-0.47f, -0.17f, -0.06f)
    private val HAND_R = floatArrayOf(0.47f, -0.17f, -0.06f)
    private val WAVE_R = floatArrayOf(0.60f, 0.40f, -0.22f)

    // The robot's own dice (the desktop's note: bases in the gaps the animals leave).
    private const val S_GAZE = 77
    private const val S_EVENT = 157
    private const val S_BEAT = 237
    private const val S_BLINK = 244
    private const val S_LEAN = 135
    private const val S_ZIP = 158
    private const val S_SIDE = 254
    private const val S_LISTEN = 78
    private const val S_THINK = 79
    private const val S_FOCUS = 239
    private const val S_NOD = 252
    private const val S_PHRASE = 253
    private const val S_CUTE = 251
    private const val S_BAG = 243
    /** How long each cute moment lasts: the wave, polishing its visor. */
    private val CUTE_LEN = floatArrayOf(3.3f, 3.2f)

    // Idle: 16-second slots, sixteen to a 256-second window (the desktop's notes).
    private const val SLOT = 16f
    private const val REST_S = 10f
    // fin flick, curious look, hover dip, look at its mitten, happy squint
    private val SMALL = floatArrayOf(22f, 20f, 18f, 18f, 22f)
    private const val K_ZIP = 5f

    /** What it does at rest at clock [t]: [kind, seconds since it started, the clock it starts at] (the desktop's idleEvent). */
    private fun idleEvent(t: Float): FloatArray {
        val n = floor(t / SLOT).toInt()
        val m = n and 255
        val pos = m and 15
        if ((pos == 0 || pos == 6 || pos == 13) && hash01(m * 256 + S_ZIP) < 0.75f) {
            val off = 0.5f + 5.5f * hash01(m * 256 + S_EVENT + 2)
            return floatArrayOf(K_ZIP, t - n * SLOT - off, n * SLOT + off)
        }
        return happening(t, SLOT, 0.5f, 5.5f, S_EVENT, 0.7f, SMALL)
    }

    /** Which way a happening starting at clock [at] goes, -1 or 1. */
    private fun sideOf(at: Float): Float = if (hash01((floor(at / SLOT).toInt() and 255) * 256 + S_SIDE) < 0.5f) -1f else 1f

    /** Whether one of its idle moments is playing at clock [t] - the desktop's busy(state, t, since, opts). */
    fun busy(state: FaceState, t: Float, since: Float? = null, opts: Opts? = null): Boolean =
        state == FaceState.IDLE && (CritterPose.playing(idleEvent(t)) || cuteBusy(t, since, opts, S_CUTE, CUTE_LEN))

    /** The zip: where it is, [x] seconds in, from its resting place (the desktop's zipAt). */
    private const val ZIP_S = 2.6f
    private fun zipAt(x: Float, at: Float): FloatArray {
        if (x <= 0f || x >= ZIP_S) return floatArrayOf(0f, 0f, 0f)
        val m = floor(at / SLOT).toInt() and 255
        val tx = 0.22f * (2f * hash01(m * 256 + S_ZIP + 1) - 1f)
        val ty = 0.03f + 0.10f * hash01(m * 256 + S_ZIP + 2)
        val tz = 0.45f + 0.40f * hash01(m * 256 + S_ZIP + 3)
        val dir = if (hash01(m * 256 + S_ZIP + 4) < 0.5f) -1f else 1f
        val go = ease(x / 0.7f) - ease((x - 1.75f) / 0.85f)
        val th = TAU * ease((x - 0.55f) / 1.3f)
        val r = 0.10f
        return floatArrayOf(tx * go + dir * r * sin(th), ty * go + r * (1f - cos(th)), tz * go)
    }
    /** Whether a zip starting [x] seconds ago may play (the desktop's zipClear). */
    private fun zipClear(t: Float, since: Float, x: Float): Float {
        val s0 = since - x
        if (s0 < REST_S) return 0f
        for (d in floatArrayOf(0f, 0.5f * ZIP_S, ZIP_S)) {
            if (cuteAt(t - x + d, s0 + d, S_CUTE, CUTE_LEN)[0] >= 0f) return 0f
        }
        return 1f
    }

    /** A talking gesture when the host gives no phrase ends - the desktop's beat(): five kinds. */
    private val BEAT = floatArrayOf(3f, 2f, 2f, 2f, 2f)
    private fun beat(t: Float): FloatArray {
        val b = happening(t, 2f, 0f, 0.6f, S_BEAT, 0.45f, BEAT)
        if (b[0] < 0f) return b
        fun atYou(id: Int) = hash01(id * 256 + S_GAZE + 5) < 0.65f
        fun moves(c: CritterPose.Chain) = !(atYou(c.id) && atYou(c.prev))
        val c = chain(b[2], 32f, S_GAZE, 1.6f, 5.5f, 1.3f)
        if (c.since < 1.5f && moves(c)) return NONE
        val n = chain(b[2] + 1.5f, 32f, S_GAZE, 1.6f, 5.5f, 1.3f)
        if (n.id != c.id && moves(n)) return NONE
        return b
    }
    /** The five kinds from a phrase-end gesture's three (the desktop's phraseKind). */
    private fun phraseKind(k: Int, n: Int): Int {
        if (k == 0) return 0
        if (k == 1) return if (hash01((n and 4095) * 256 + S_BAG) < 0.5f) 1 else 2
        return if (hash01((n and 4095) * 256 + S_BAG + 1) < 0.5f) 3 else 4
    }

    /** [v], held softly inside -k..k (the desktop's soft). */
    private fun soft(v: Float, k: Float): Float = k * tanh(v / k)

    private fun headTurn(p: FloatArray): FloatArray = mul(ry(-p[HEAD_YAW]), mul(rx(p[HEAD_PITCH]), rz(-p[HEAD_ROLL])))
    /** A point in the head's frame, in the body's frame. */
    private fun onHead(p: FloatArray, x: Float, y: Float, z: Float): FloatArray {
        val v = apply(headTurn(p), x, y, z)
        return floatArrayOf(NECK[0] + v[0], NECK[1] + v[1], NECK[2] + v[2])
    }
    private fun handL(p: FloatArray, v: FloatArray, w: Float) {
        p[L_HX] += (v[0] - p[L_HX]) * w; p[L_HY] += (v[1] - p[L_HY]) * w; p[L_HZ] += (v[2] - p[L_HZ]) * w
    }
    private fun handR(p: FloatArray, v: FloatArray, w: Float) {
        p[R_HX] += (v[0] - p[R_HX]) * w; p[R_HY] += (v[1] - p[R_HY]) * w; p[R_HZ] += (v[2] - p[R_HZ]) * w
    }

    /** The small reaction as waiting on you or an error arrives; returns how far the eyes shut (the desktop's react). */
    private const val ARRIVE_S = 1.3f
    private fun react(p: FloatArray, state: FaceState, x: Float, k: Int, w: Float): Float {
        if (k < 0 || w <= 0f || x <= 0f || x >= ARRIVE_S) return 0f
        if (state == FaceState.APPROVAL) {
            if (k == 0) {
                val b = w * bump(x / 1.0f)
                p[POS_Y] += 0.022f * b; p[FIN_L] -= 0.18f * b; p[FIN_R] -= 0.18f * b
                return 0f
            }
            if (k == 1) {
                p[SIZE] += 0.07f * w * bump((x - 0.2f) / 0.8f)
                return w * bump(x / 0.3f)
            }
            val b = w * bump(x / 1.1f)
            p[PITCH] += 0.05f * b; p[POS_Z] -= 0.03f * b; p[HEAD_PITCH] += 0.03f * b
            return 0f
        }
        if (k == 0) {
            val b = w * bump(x / 0.9f)
            p[POS_Z] += 0.035f * b
            return 0.35f * b
        }
        if (k == 1) {
            val b = w * bump(x / 1.2f)
            p[FIN_L] += 0.2f * b; p[FIN_R] += 0.2f * b
            return w * bump((x - 0.1f) / 0.6f)
        }
        val b = w * bump(x / 1.2f)
        p[LOOK_Y] -= 0.35f * b; p[HEAD_PITCH] -= 0.05f * b
        return 0f
    }

    fun stateTargets(state: FaceState, t: Float, amp: Float, look: Look, since: Float = 1e9f, o0: Opts = Opts()): FloatArray {
        val o = o0.norm(t)
        // Idle: a focus session, and a cute moment while it plays, take the happenings away.
        val cu = if (state == FaceState.IDLE) cuteAt(t, since, S_CUTE, CUTE_LEN) else NONE
        val cw = if (cu[0] >= 0f) cuteOf(o) else 0f
        val fw = if (state == FaceState.IDLE) focusOf(o) else 0f
        val hap = o.hap * (1f - fw) * (1f - cw * (if (cu[0] >= 0f) cuteQuiet(cu[1], CUTE_LEN[cu[0].toInt()]) else 0f))
        val sw = o.sway
        val play = o.play
        val zipW = (1f - o.still) * (1f - o.calm) * (1f - o.serious) * (1f - o.quiet) * (1f - fw) *
            (1f - (if (awake(state)) petOf(o) else 0f))
        val p = FloatArray(N)
        p[EYE_L] = 1f; p[EYE_R] = 1f; p[SIZE] = 1f; p[GLOW] = 1f
        p[FIN_L] = 0.12f; p[FIN_R] = 0.12f; p[FIN_GLOW] = 0.5f; p[GLEAM] = -1f
        p[L_HX] = HAND_L[0]; p[L_HY] = HAND_L[1]; p[L_HZ] = HAND_L[2]
        p[R_HX] = HAND_R[0]; p[R_HY] = HAND_R[1]; p[R_HZ] = HAND_R[2]
        p[ASLEEP] = if (state == FaceState.STANDBY) 1f else 0f
        // 300 cycles a loop: once every 3.4 seconds.
        var bobK = 300f
        var bobA = 0.018f
        var blinkSlow = 1f
        var blinks = true
        var turnBlink = 0f
        var lid = 1f
        var ackK = 1f
        var chin = 0f
        var polish = 0f
        var rub = 0f
        var waveUp = 0f
        var waving = 0f
        var zip: FloatArray? = null

        when (state) {
            FaceState.LISTENING -> {
                // Wide round eyes on you, head tilted, fins leaning in, mittens up and open.
                val g = looks(t, S_GAZE, 1.8f, 6f, 0.85f, 0.2f, 0.1f, 0f, 0.04f, 1.1f, o)
                p[HEAD_ROLL] = play * 0.24f + sw * 0.02f * wave(t, 205f, 0f)
                p[HEAD_YAW] = 0.1f * g[2]
                p[HEAD_PITCH] = 0.03f
                p[PITCH] = 0.06f
                p[FIN_L] = -0.14f; p[FIN_R] = -0.14f
                p[EYE_L] = 1.05f + 0.1f * play; p[EYE_R] = p[EYE_L]
                p[SIZE] = 1.06f + 0.06f * play
                p[LOOK_X] = g[0] - 0.4f * g[2]; p[LOOK_Y] = 0.05f + g[1] - 0.4f * g[3]
                p[GLOW] = 1.05f + 0.35f * amp
                p[FIN_GLOW] = 0.6f + 0.4f * amp
                p[L_HX] = -0.40f; p[L_HY] = -0.03f; p[L_HZ] = -0.20f; p[R_HX] = 0.40f; p[R_HY] = -0.03f; p[R_HZ] = -0.20f
                // Now and then (variety): the other tilt, leaning closer, one fin turned.
                val v = variant(t, o, S_LISTEN, 0.4f)
                if (v[0] == 0f) p[HEAD_ROLL] -= 0.40f * play * v[1]
                else if (v[0] == 1f) { p[PITCH] += 0.04f * v[1]; p[POS_Z] -= 0.03f * v[1]; p[FIN_L] -= 0.08f * v[1]; p[FIN_R] -= 0.08f * v[1] }
                else if (v[0] == 2f) p[FIN_R] -= 0.25f * v[1]
                // A small nod in your pauses, its fins flicking.
                val nd = listenNod(t, o, S_NOD)
                p[HEAD_PITCH] += nd[0]; p[HEAD_ROLL] += play * nd[1]; lid *= 1f - nd[2]
                p[FIN_L] -= 0.25f * nd[3]; p[FIN_R] -= 0.25f * nd[3]
                turnBlink = g[4]
            }
            FaceState.THINKING -> {
                // Narrowed eyes looking up, scanning; a mitten to its chin.
                val g = looks(t, S_GAZE, 1.8f, 6f, 0.3f, 0.5f, 0.15f, 0.5f, 0.04f, 1.1f, o)
                p[SQUINT] = 0.6f; p[SIZE] = 0.96f
                p[LOOK_X] = sw * 0.45f * wave(t, 150f, 0f) + 0.3f * g[0] - 0.3f * g[2]
                p[LOOK_Y] = 0.75f + 0.15f * g[1] - 0.3f * g[3]
                p[HEAD_PITCH] = 0.07f + 0.1f * g[3] + sw * 0.02f * wave(t, 147f, 0f)
                p[HEAD_YAW] = 0.12f * g[2] + sw * 0.05f * wave(t, 150f, 0.4f)
                p[HEAD_ROLL] = play * 0.06f + sw * 0.03f * wave(t, 98f, 0f)
                p[GLOW] = 0.95f + 0.15f * wave(t, 300f, 0f)
                p[FIN_GLOW] = 0.8f
                chin = 1f
                // Now and then (variety): mittens tapping, a tilt with a fin twitch, a look down.
                val v = variant(t, o, S_THINK, 0.5f)
                if (v[0] == 0f) {
                    val gate = ease(0.5f + 1.5f * wave(t, 184f, 0f))
                    val taps = sw * (0.5f - 0.5f * wave(t, 1141f, HALF_PI)).pow(2) * gate
                    chin = 1f - v[1]
                    handL(p, floatArrayOf(-0.11f, -0.10f + 0.02f * taps, -0.31f), v[1])
                    handR(p, floatArrayOf(0.11f, -0.10f + 0.02f * taps, -0.31f), v[1])
                } else if (v[0] == 1f) {
                    p[HEAD_ROLL] += 0.10f * play * v[1]
                    p[FIN_R] += sw * 0.12f * v[1] * wave(t, 400f, 0f)
                } else if (v[0] == 2f) {
                    p[LOOK_Y] += (-0.4f - p[LOOK_Y]) * v[1]; p[HEAD_PITCH] -= 0.12f * v[1]
                }
                turnBlink = g[4]
            }
            FaceState.SPEAKING -> {
                // Bright eyes that pulse with the voice (uniforms); head and mittens talk in phrases.
                val g = looks(t, S_GAZE, 1.6f, 5.5f, 0.65f, 0.5f, 0.18f, 0f, 0.06f, 1.1f, o)
                var b = beat(t)
                if (o.phraseN >= 0) {
                    val pb = phraseBeat(t, o, S_PHRASE, S_GAZE, 1.6f, 5.5f, 0.65f)
                    b = if (pb[0] < 0f) pb else floatArrayOf(phraseKind(pb[0].toInt(), max(0, o.phraseN)).toFloat(), pb[1], pb[2])
                }
                val x = b[1]
                ackK = if (b[0] >= 0f) 1f - bump(clamp(x / 1.6f, 0f, 1f)) else 1f
                p[SPEAK] = 1f
                p[HAPPY] = 0.55f; p[SIZE] = 1.02f; p[GLOW] = 1.1f; p[FIN_GLOW] = 0.7f
                p[PITCH] = 0.03f
                p[HEAD_YAW] = sw * 0.05f * wave(t, 111f, 0f) + 0.09f * g[2]
                p[HEAD_ROLL] = sw * 0.04f * wave(t, 93f, 0.5f)
                p[LOOK_X] = g[0] - 0.16f * g[2]; p[LOOK_Y] = g[1] - 0.16f * g[3]
                p[L_HX] = -0.47f; p[L_HY] = -0.12f; p[L_HZ] = -0.12f; p[R_HX] = 0.47f; p[R_HY] = -0.12f; p[R_HZ] = -0.12f
                if (b[0] == 0f) {
                    p[HEAD_PITCH] -= hap * 0.07f * (bump(x / 0.7f) - 0.3f * bump((x - 0.55f) / 0.7f))
                    p[HAPPY] += hap * 0.3f * bump(x / 0.7f)
                } else if (b[0] == 1f || b[0] == 2f) {
                    val e = hap * envAHR(x, 0.4f, 0.35f, 0.6f)
                    if (b[0] == 1f) {
                        p[R_HX] += 0.06f * e; p[R_HY] += 0.14f * e; p[R_HZ] -= 0.10f * e; p[FIN_R] -= 0.12f * e
                    } else {
                        p[L_HX] -= 0.06f * e; p[L_HY] += 0.14f * e; p[L_HZ] -= 0.10f * e; p[FIN_L] -= 0.12f * e
                    }
                } else if (b[0] == 3f) {
                    val e = hap * envAHR(x, 0.45f, 0.3f, 0.6f)
                    p[L_HX] -= 0.05f * e; p[L_HY] += 0.10f * e; p[L_HZ] -= 0.08f * e
                    p[R_HX] += 0.05f * e; p[R_HY] += 0.10f * e; p[R_HZ] -= 0.08f * e
                    p[SIZE] += 0.04f * e
                } else if (b[0] == 4f) {
                    p[HEAD_ROLL] += hap * play * 0.08f * bump(x / 1.2f)
                    p[FIN_L] -= hap * 0.2f * bump((x - 0.2f) / 0.6f)
                }
                turnBlink = g[4]
            }
            FaceState.APPROVAL -> {
                // Steady round eyes on you, fins up, mittens a little forward, leaning in;
                // hovering almost still. No wave, nothing cute - one small reaction as it arrives.
                val g = restingGaze(t, S_GAZE)
                p[EYE_L] = 1.06f; p[EYE_R] = 1.06f
                p[SIZE] = 1.04f + 0.03f * play
                p[GLOW] = 1.1f; p[FIN_GLOW] = 0.7f; p[FIN_L] = -0.06f; p[FIN_R] = -0.06f
                p[PITCH] = 0.05f; p[HEAD_PITCH] = 0.03f
                p[L_HX] = -0.41f; p[L_HY] = -0.11f; p[L_HZ] = -0.18f; p[R_HX] = 0.41f; p[R_HY] = -0.11f; p[R_HZ] = -0.18f
                p[LOOK_X] = g[0]; p[LOOK_Y] = g[1]
                blinkSlow = 1.4f; bobA = 0.006f
                lid *= 1f - react(p, state, since, o.arrive, varOf(o))
            }
            FaceState.STANDBY -> {
                // Powered down: eyes a dim line, head bowed, fins drooping.
                val e = happening(t, 16f, 0.5f, 5.5f, S_EVENT, 0.35f, 1)
                val sigh = if (e[0] == 0f) bump(e[1] / 4.5f) else 0f
                p[EYE_L] = 0f; p[EYE_R] = 0f
                p[GLOW] = 0.4f; p[FIN_GLOW] = 0.12f; p[FIN_L] = 0.50f; p[FIN_R] = 0.50f
                p[HEAD_PITCH] = -0.16f - 0.03f * sigh; p[HEAD_ROLL] = 0.08f * play; p[PITCH] = 0.04f
                p[POS_Y] = -0.08f - 0.01f * sigh
                p[L_HX] = -0.40f; p[L_HY] = -0.26f; p[L_HZ] = -0.02f; p[R_HX] = 0.40f; p[R_HY] = -0.26f; p[R_HZ] = -0.02f
                bobK = 171f; bobA = 0.008f * (1f + 0.6f * sigh); blinks = false
            }
            FaceState.ERROR -> {
                // A still, concerned look. Nothing comic.
                val g = restingGaze(t, S_GAZE)
                p[SLANT] = 0.30f; p[SQUINT] = 0.45f; p[SIZE] = 0.92f; p[EYE_L] = 0.85f; p[EYE_R] = 0.85f; p[GLOW] = 0.85f
                p[HEAD_ROLL] = -0.10f * play; p[HEAD_PITCH] = -0.07f
                p[LOOK_X] = g[0]; p[LOOK_Y] = -0.3f + g[1]
                p[FIN_L] = 0.40f; p[FIN_R] = 0.40f; p[FIN_GLOW] = 0.3f
                p[L_HX] = -0.42f; p[L_HY] = -0.24f; p[L_HZ] = -0.04f; p[R_HX] = 0.42f; p[R_HY] = -0.24f; p[R_HZ] = -0.04f
                p[POS_Y] = -0.02f
                blinkSlow = 1.4f; bobA = 0.006f
                lid *= 1f - react(p, state, since, o.arrive, varOf(o))
            }
            FaceState.BANKED -> {
                // Dozing where it floats; now and then its head sinks and it catches itself.
                val e = happening(t, 16f, 0.5f, 5.5f, S_EVENT, 0.55f, 1)
                val x = e[1]
                val droop = if (e[0] == 0f) {
                    if (x < 3.2f) ease(x / 3.2f) else 1f - ease((x - 3.2f) / 0.8f)
                } else 0f
                p[EYE_L] = 0.35f * (1f - 0.7f * droop); p[EYE_R] = p[EYE_L]
                p[SQUINT] = 0.3f; p[GLOW] = 0.6f; p[FIN_GLOW] = 0.3f; p[FIN_L] = 0.3f; p[FIN_R] = 0.3f
                p[HEAD_PITCH] = -0.12f - 0.12f * droop
                p[LOOK_Y] = -0.2f
                p[POS_Y] = -0.03f
                bobK = 205f; bobA = 0.012f; blinkSlow = 2.5f
            }
            FaceState.IDLE -> {
                // Happy arcs, looking about; now and then a small thing, a zip or a cute moment.
                val g = looks(t, S_GAZE, 1.4f, 5.5f, 0.4f, 0.8f, 0.3f, 0.05f, 0.07f, 1.1f, o)
                val ev = idleEvent(t)
                val x = ev[1]
                p[HAPPY] = 0.85f
                p[HEAD_YAW] = 0.22f * g[2]
                p[HEAD_PITCH] = 0.08f * g[3] + sw * 0.015f * wave(t, 97f, 1.1f)
                p[HEAD_ROLL] = sw * 0.03f * wave(t, 71f, 0.2f)
                p[ROLL] = sw * 0.02f * shift(t, S_LEAN)
                p[POS_X] = sw * 0.01f * wave(t, 131f, 0.4f)
                p[LOOK_X] = g[0] - 0.4f * g[2]; p[LOOK_Y] = g[1] - 0.4f * g[3]
                p[FIN_L] += sw * 0.05f * wave(t, 173f, 0f); p[FIN_R] += sw * 0.05f * wave(t, 173f, 1.9f)
                p[L_HY] += sw * 0.008f * wave(t, 113f, 0f); p[R_HY] += sw * 0.008f * wave(t, 113f, 1.5f)
                when (ev[0]) {
                    0f -> {
                        // A fin flicks, then the other.
                        val s = sideOf(ev[2])
                        val a = hap * 0.35f * bump(x / 0.5f)
                        val b = hap * 0.22f * bump((x - 0.35f) / 0.5f)
                        if (s < 0f) { p[FIN_L] += a; p[FIN_R] += b } else { p[FIN_R] += a; p[FIN_L] += b }
                    }
                    1f -> {
                        // A curious look to one side.
                        val s = sideOf(ev[2])
                        val e = hap * envAHR(x, 0.5f, 1.6f, 0.7f)
                        p[HEAD_YAW] += (s * 0.28f - p[HEAD_YAW]) * e
                        p[HEAD_ROLL] += s * 0.10f * play * e
                        p[HAPPY] += (0.15f - p[HAPPY]) * e; p[SIZE] += 0.08f * e
                        p[LOOK_X] += (s * 0.7f - p[LOOK_X]) * e; p[LOOK_Y] += (0.1f - p[LOOK_Y]) * e
                    }
                    2f -> {
                        // A small dip and rise, with a blink.
                        val d = hap * bump(x / 1.6f)
                        p[POS_Y] -= 0.035f * d
                        p[FIN_L] += 0.08f * d; p[FIN_R] += 0.08f * d
                        lid = 1f - hap * bump((x - 0.55f) / 0.35f)
                    }
                    3f -> {
                        // It looks at its left mitten and wiggles it.
                        val e = hap * envAHR(x, 0.6f, 1.4f, 0.7f)
                        handL(p, floatArrayOf(-0.30f, 0.02f, -0.30f), e)
                        p[L_HX] += 0.02f * e * wave(t, 900f, 0f)
                        p[HEAD_PITCH] -= 0.14f * e; p[HEAD_YAW] -= 0.10f * e
                        p[LOOK_X] += (-0.35f - p[LOOK_X]) * e; p[LOOK_Y] += (-0.6f - p[LOOK_Y]) * e
                        p[HAPPY] += (0.3f - p[HAPPY]) * e
                    }
                    4f -> {
                        // A happy squint.
                        val e = hap * envAHR(x, 0.4f, 1.4f, 0.6f)
                        p[HAPPY] += (1f - p[HAPPY]) * e; p[SIZE] += 0.05f * e
                        lid = 1f - 0.3f * e
                        p[HEAD_ROLL] += sideOf(ev[2]) * 0.08f * play * e
                    }
                    K_ZIP -> zip = floatArrayOf(x, ev[2], zipW * zipClear(t, since, x))
                }
                turnBlink = g[4]
                if (fw > 0f) {
                    // Working beside you: mittens together in front, tinkering, eyes on them.
                    val f = gaze(t, S_FOCUS, 4f, 12f, 0.75f, 0.3f, 0.12f, 0f, 0.03f, 1.6f)
                    p[LOOK_X] += (f[0] - 0.4f * f[2] - p[LOOK_X]) * fw
                    p[LOOK_Y] += (-0.6f + f[1] - 0.4f * f[3] - p[LOOK_Y]) * fw
                    p[HEAD_YAW] += (0.2f * f[2] - p[HEAD_YAW]) * fw
                    p[HEAD_PITCH] += (-0.14f + 0.1f * f[3] - p[HEAD_PITCH]) * fw
                    handL(p, floatArrayOf(-0.14f, -0.14f + 0.01f * sw * wave(t, 260f, 0f), -0.30f), fw)
                    handR(p, floatArrayOf(0.14f, -0.14f + 0.01f * sw * wave(t, 260f, 2.1f), -0.30f), fw)
                    p[HAPPY] += (0.5f - p[HAPPY]) * fw
                    turnBlink *= 1f - fw
                }
                // The small stretch as a focus session ends.
                val fe = focusEndOf(t, o)
                if (fe > 0f) {
                    handL(p, floatArrayOf(-0.55f, 0.22f, -0.08f), 0.8f * fe); handR(p, floatArrayOf(0.55f, 0.22f, -0.08f), 0.8f * fe)
                    p[HEAD_PITCH] += 0.08f * fe; p[FIN_L] -= 0.25f * fe; p[FIN_R] -= 0.25f * fe
                    p[HAPPY] += (1f - p[HAPPY]) * fe; lid *= 1f - 0.5f * fe
                }
                if (cw > 0f && cu[0] == 0f) {
                    // Cute moment: a friendly wave.
                    val xc = cu[1]
                    waveUp = cw * envAHR(xc, 0.6f, 1.9f, 0.7f)
                    waving = cw * envAHR(xc - 0.5f, 0.3f, 1.5f, 0.4f)
                    p[HAPPY] += (1f - p[HAPPY]) * waveUp; p[SIZE] += 0.04f * waveUp
                    p[HEAD_ROLL] += 0.10f * play * waveUp; p[HEAD_YAW] += 0.06f * waveUp
                    p[ROLL] -= 0.03f * waveUp
                    p[FIN_R] -= 0.15f * waveUp
                    p[LOOK_X] += (0f - p[LOOK_X]) * waveUp; p[LOOK_Y] += (0f - p[LOOK_Y]) * waveUp
                    turnBlink *= 1f - waveUp
                } else if (cw > 0f && cu[0] == 1f) {
                    // Cute moment: it polishes its visor; a gleam crosses it.
                    val xc = cu[1]
                    polish = cw * envAHR(xc, 0.7f, 1.6f, 0.7f)
                    rub = envAHR(xc - 0.6f, 0.3f, 1.3f, 0.4f)
                    p[HAPPY] += (1f - p[HAPPY]) * polish
                    lid *= 1f - 0.45f * polish * rub
                    p[HEAD_PITCH] -= 0.10f * polish; p[HEAD_ROLL] -= 0.08f * play * polish
                    p[LOOK_X] += (0f - p[LOOK_X]) * polish; p[LOOK_Y] += (0f - p[LOOK_Y]) * polish
                    if (xc > 2.4f && xc < 3.15f) p[GLEAM] = (xc - 2.4f) / 0.75f
                    val fl = cw * bump((xc - 2.4f) / 0.6f)
                    p[FIN_L] -= 0.25f * fl; p[FIN_R] -= 0.25f * fl
                    turnBlink *= 1f - polish
                }
            }
        }

        // Stroked: it leans its head into your hand, eyes smiling, fins back.
        val pw = if (awake(state)) petOf(o) else 0f
        if (pw > 0f) {
            p[HEAD_ROLL] += pw * play * (0.10f * o.petX + 0.03f * o.petDir)
            p[HEAD_PITCH] += 0.04f * pw
            p[ROLL] -= 0.02f * pw * o.petX
            p[FIN_L] += 0.2f * pw; p[FIN_R] += 0.2f * pw
            p[HAPPY] += (1f - p[HAPPY]) * pw
            lid *= 1f - 0.45f * pw
        }
        // A fact saved: a small nod, fins flicking. A long answer ready: eyes and fins glow up once.
        val an = if (awake(state)) ackNodOf(t, o) else ZERO2
        p[HEAD_PITCH] += ackK * an[0]; p[FIN_L] -= 0.3f * ackK * an[1]; p[FIN_R] -= 0.3f * ackK * an[1]
        val gl = if (awake(state)) ackGlowOf(t, o) else 0f
        p[GLOW] += 0.4f * gl; p[FIN_GLOW] += 0.6f * gl

        // The hover, and the fins trailing it.
        val hb = wave(t, bobK, 0f)
        p[POS_Y] += bobA * (1f - 0.4f * o.calm) * hb
        val trail = 0.25f * bobA * (1f - 0.4f * o.calm) * wave(t - 0.35f, bobK, 0f) / 0.018f
        p[FIN_L] += 0.04f * trail; p[FIN_R] += 0.04f * trail

        // The pointer: mostly with the eyes. Asleep, it does not follow.
        val lw = if (state == FaceState.STANDBY) 0f else clamp(look.w, 0f, 1f)
        if (lw > 0f) {
            val lx = clamp(look.x, -1f, 1f)
            val ly = clamp(look.y, -1f, 1f)
            p[LOOK_X] += (lx - p[LOOK_X]) * lw
            p[LOOK_Y] += (ly - p[LOOK_Y]) * lw
            p[HEAD_YAW] += o.head * 0.2f * lx * lw
            p[HEAD_PITCH] += o.head * 0.2f * ly * lw
        }

        // What the mittens do to the head, now that it has turned.
        if (chin > 0f) handR(p, onHead(p, 0.21f, 0.01f, -0.30f), chin)
        if (polish > 0f) {
            val q = onHead(
                p, 0.14f + 0.05f * rub * wave(t, 1280f, HALF_PI), HC_Y - 0.10f + 0.045f * rub * wave(t, 1280f, 0f), -0.52f,
            )
            handR(p, q, polish)
        }
        if (waveUp > 0f) {
            handR(p, WAVE_R, waveUp)
            p[R_HX] += 0.06f * waving * wave(t, 1741f, 0f)
            p[R_HZ] -= 0.02f * waving * wave(t, 1741f, HALF_PI)
        }
        val z = zip
        if (z != null && z[2] > 0f) {
            // The dash, banking into each turn, eyes looking where it goes.
            val k = z[2]
            val pz = zipAt(z[0], z[1])
            val h = 1f / 30f
            val a = zipAt(z[0] + h, z[1])
            val b = zipAt(z[0] - h, z[1])
            val vx = k * (a[0] - b[0]) / (2f * h)
            val vy = k * (a[1] - b[1]) / (2f * h)
            val vz = k * (a[2] - b[2]) / (2f * h)
            val v2 = vx * vx + vy * vy + vz * vz
            val sp = v2 / (v2 + 0.5f)
            p[POS_X] += k * pz[0]; p[POS_Y] += k * pz[1]; p[POS_Z] += k * pz[2]
            p[ROLL] -= 0.22f * soft(vx, 1.4f)
            p[PITCH] += 0.10f * soft(-vz, 1.4f) + 0.05f * soft(vy, 1.4f)
            p[HAPPY] += (1f - p[HAPPY]) * sp
            p[LOOK_X] += 0.35f * soft(vx, 1.0f); p[LOOK_Y] += 0.25f * soft(vy, 1.0f)
            p[L_HX] -= 0.03f * vx; p[L_HY] -= 0.03f * vy; p[R_HX] -= 0.03f * vx; p[R_HY] -= 0.03f * vy
            p[FIN_L] += 0.10f * sp; p[FIN_R] += 0.10f * sp
        }
        lid *= farewell(p, state, o)

        val qk = 1f - o.quiet
        val k = lid * (1f - qk * max(if (blinks) blinkAt(t, S_BLINK, blinkSlow, 2f, 9f) else 0f, turnBlink))
        p[EYE_L] *= k
        p[EYE_R] *= k
        return p
    }

    /** Hello and goodbye (the desktop's farewell, and its notes); returns how open the eyes are. */
    private const val UP = 2.3f
    private const val DOWN = 2.1f
    private fun farewell(p: FloatArray, state: FaceState, o: Opts): Float {
        val g = o.goodbye
        val h = o.hello
        if (g <= 0f && h >= 1f) return 1f
        val e = extras(o)
        val awakeK = if (awake(state) || state == FaceState.APPROVAL || state == FaceState.ERROR) 1f else 0f
        val wave1 = if (awake(state)) 1f else 0f
        var lid = 1f
        if (g > 0f) {
            val a = e * bump(clamp(g / 0.6f, 0f, 1f))
            val at = e * awakeK * ease(g / 0.2f)
            p[LOOK_X] += (0f - p[LOOK_X]) * at; p[LOOK_Y] += (0f - p[LOOK_Y]) * at
            p[HEAD_YAW] += (0f - p[HEAD_YAW]) * at
            val wv = a * wave1
            handR(p, WAVE_R, wv)
            p[R_HX] += 0.06f * wv * sin(TAU * 1.6f * g)
            p[HAPPY] += (1f - p[HAPPY]) * wv
            val bw = a * (awakeK - wave1)
            p[HEAD_PITCH] -= 0.2f * bw; p[PITCH] += 0.04f * bw
            val go = e * ease((g - 0.45f) / 0.55f)
            p[POS_Y] += UP * go; p[POS_Z] += 0.2f * go
            p[FIN_L] += 0.2f * go; p[FIN_R] += 0.2f * go
        }
        if (h < 1f) {
            lid *= toward(1f, ease((h - 0.35f) / 0.3f) * (1f - bump((h - 0.72f) / 0.18f)), e)
            p[POS_Y] += e * (DOWN * (1f - ease(h / 0.55f)) - 0.045f * bump((h - 0.52f) / 0.33f))
            val f = e * bump((h - 0.6f) / 0.3f)
            p[FIN_L] -= 0.25f * f; p[FIN_R] -= 0.25f * f
            val at = e * awakeK * ease((h - 0.4f) / 0.2f) * (1f - ease((h - 0.85f) / 0.15f))
            p[LOOK_X] += (0f - p[LOOK_X]) * at; p[LOOK_Y] += (0f - p[LOOK_Y]) * at
            p[HEAD_YAW] += (0f - p[HEAD_YAW]) * at
            p[HAPPY] += (1f - p[HAPPY]) * e * wave1 * bump((h - 0.6f) / 0.4f)
        }
        return lid
    }

    private val FINS = intArrayOf(FIN_L, FIN_R)
    private val HANDS = intArrayOf(L_HX, L_HY, L_HZ, R_HX, R_HY, R_HZ)
    private val HEAD = intArrayOf(HEAD_YAW, HEAD_PITCH, HEAD_ROLL)
    private fun hold(p: FloatArray, f: FloatArray, keys: IntArray, w: Float) {
        for (i in keys) p[i] = toward(p[i], f[i], w)
    }

    /** Its powering down and booting up - the desktop's wakeSleep, and its notes. */
    private fun wakeSleep(p: FloatArray, state: FaceState, x: Float, k: Float, ex: Float, t: Float, f: FloatArray?) {
        val e = ex * k
        if (state == FaceState.STANDBY && f != null) {
            val lids = (1f - 0.3f * ease((x - 0.3f) / 0.7f)) * (1f - ease((x - 1.6f) / 1.0f))
            val lid = k * toward(eyesClose(x), lids, ex)
            p[EYE_L] = f[EYE_L] * lid; p[EYE_R] = f[EYE_R] * lid
            val shape = k * (1f - ease((x - 2.2f) / 0.8f))
            p[HAPPY] = toward(p[HAPPY], f[HAPPY], shape); p[SIZE] = toward(p[SIZE], f[SIZE], shape)
            p[SQUINT] = toward(p[SQUINT], f[SQUINT], shape); p[SLANT] = toward(p[SLANT], f[SLANT], shape)
            p[GLOW] = toward(p[GLOW], f[GLOW], k * (1f - ease((x - 1.2f) / 1.6f)))
            hold(p, f, FINS, e * (1f - ease((x - 1.0f) / 1.6f)))
            hold(p, f, HANDS, e * (1f - ease((x - 0.8f) / 1.8f)))
            hold(p, f, HEAD, e * (1f - ease((x - 1.4f) / 1.4f)))
            return
        }
        val lids = ease((x - 0.45f) / 0.5f) * (1f - ex * bump((x - 1.15f) / 0.35f))
        val fe = 1f - k * (1f - lids)
        p[EYE_L] *= fe; p[EYE_R] *= fe
        p[FIN_L] -= 0.25f * e * bump((x - 1.3f) / 0.6f); p[FIN_R] -= 0.25f * e * bump((x - 1.4f) / 0.6f)
        p[POS_Y] += 0.02f * e * bump((x - 0.9f) / 0.9f)
    }

    // (The eyes' shape and glow settle with the body - the desktop's note.)
    internal val HALF = CritterPose.halfLives(
        N,
        intArrayOf(EYE_L, EYE_R, LOOK_X, LOOK_Y, GLEAM), intArrayOf(SPEAK), intArrayOf(HEAD_YAW, HEAD_PITCH, HEAD_ROLL),
        intArrayOf(L_HX, L_HY, L_HZ, R_HX, R_HY, R_HZ, FIN_GLOW),
        intArrayOf(FIN_L, FIN_R),
    )

    /** How much this pose is speaking, 0..1 - what [uniforms] scales the eyes' pulse by. */
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

    /** The whole robot's turn, and where the middle of its body is (world). */
    private fun frameOf(p: FloatArray): FloatArray = mul(ry(-p[YAW]), mul(rz(p[ROLL]), rx(-p[PITCH])))
    private fun bodyAt(p: FloatArray): FloatArray = floatArrayOf(p[POS_X], REST_Y + p[POS_Y], p[POS_Z])

    /**
     * Uniform name to value. [mouth] is the words being heard, as for the
     * animals' mouths: the robot has none, so its eyes PULSE with the voice's
     * opening while it speaks - and not at all with no real voice.
     */
    fun uniforms(p: FloatArray, mouth: FloatArray? = null): Map<String, FloatArray> {
        val bm = frameOf(p)
        val bodyPos = bodyAt(p)
        fun toWorld(x: Float, y: Float, z: Float): FloatArray {
            val v = apply(bm, x, y, z)
            return floatArrayOf(bodyPos[0] + v[0], bodyPos[1] + v[1], bodyPos[2] + v[2])
        }
        val hm = mul(bm, headTurn(p))
        val neck = toWorld(NECK[0], NECK[1], NECK[2])
        val m = CritterPose.mouthOf(p[SPEAK], mouth)
        val pulse = clamp(m[0] + 0.3f * m[1], 0f, 1f)
        val lv = apply(hm, 0f, HC_Y - 0.08f, -0.36f)
        val out = LinkedHashMap<String, FloatArray>()
        out["uBodyPos"] = bodyPos
        out["uBodyR0"] = invRow(bm, 0); out["uBodyR1"] = invRow(bm, 1); out["uBodyR2"] = invRow(bm, 2)
        out["uNeck"] = neck
        out["uHeadR0"] = invRow(hm, 0); out["uHeadR1"] = invRow(hm, 1); out["uHeadR2"] = invRow(hm, 2)
        out["uEyes"] = floatArrayOf(clamp(p[EYE_L], 0f, 1.3f), clamp(p[EYE_R], 0f, 1.3f), clamp(p[HAPPY], 0f, 1f), clamp(p[SIZE], 0.6f, 1.4f))
        out["uEyes2"] = floatArrayOf(clamp(p[SQUINT], 0f, 1f), p[SLANT], clamp(p[GLOW], 0f, 1.6f), pulse)
        out["uLook"] = floatArrayOf(clamp(p[LOOK_X], -1f, 1f), clamp(p[LOOK_Y], -1f, 1f))
        out["uFins"] = floatArrayOf(p[FIN_L], p[FIN_R], clamp(p[FIN_GLOW], 0f, 1.5f), p[GLEAM])
        out["uShL"] = toWorld(SH_L[0], SH_L[1], SH_L[2]); out["uHandL"] = toWorld(p[L_HX], p[L_HY], p[L_HZ])
        out["uShR"] = toWorld(SH_R[0], SH_R[1], SH_R[2]); out["uHandR"] = toWorld(p[R_HX], p[R_HY], p[R_HZ])
        out["uOrb"] = floatArrayOf(neck[0] + lv[0], neck[1] + lv[1], neck[2] + lv[2], 0f)
        out["uOrbGlow"] = floatArrayOf(clamp(0.5f * p[GLOW], 0f, 1f))
        return out
    }

    // The robot's camera (robot.sksl): target x, y, z, distance, pitch.
    private val CAM = floatArrayOf(0f, -0.05f, 0f, 3.25f, 0.10f)

    /** Where its sleeping Zs rise from: [asleep, x, y] - see [CritterPose.overlay]. */
    fun overlay(p: FloatArray, yaw: Float = 0f, pitch: Float = 0f, zoom: Float = 1f): FloatArray {
        val bm = frameOf(p)
        val bp = bodyAt(p)
        val h = onHead(p, 0.36f, HC_Y + 0.40f, 0f)
        val v = apply(bm, h[0], h[1], h[2])
        return CritterPose.overlayAt(p[ASLEEP], floatArrayOf(bp[0] + v[0], bp[1] + v[1], bp[2] + v[2]), CAM, yaw, pitch, zoom)
    }
}
