package com.jarvis.client.face

import com.jarvis.client.FaceState
import kotlin.math.PI
import kotlin.math.floor

/*
 * Small rules the face shell follows, kept apart from FaceView.kt so they are
 * plain Kotlin - no Compose, no android.* - and a JVM test can check each one
 * directly. FaceView, CritterFaces and JarvisRuntime call these; nothing here
 * draws anything.
 */

/**
 * What the face says to a screen reader. The face is a live region (see
 * FaceView), so this is what TalkBack announces when it changes.
 */
object FaceWords {

    /**
     * Said while Jarvis cannot be reached - the link is down or stale (see
     * [FaceLink]). The face then shows the standby pose plus a hollow ring,
     * and it must not be read out as "notes saved for later" or "idle": both
     * would be claims about a PC this phone cannot currently hear.
     */
    const val OFFLINE = "Jarvis isn't connected"

    fun spoken(state: FaceState, offline: Boolean): String = if (offline) OFFLINE else when (state) {
        FaceState.ERROR -> "Jarvis has a problem"
        FaceState.APPROVAL -> "Jarvis is waiting for your decision"
        FaceState.LISTENING -> "Jarvis is listening"
        FaceState.THINKING -> "Jarvis is working"
        FaceState.SPEAKING -> "Jarvis is speaking"
        FaceState.BANKED -> "Jarvis has notes saved for later"
        FaceState.STANDBY -> "Jarvis is on standby and will not speak"
        FaceState.IDLE -> "Jarvis is idle"
    }
}

/**
 * What the face shows while the link to the PC is cut - down, or up but
 * stale (no events arriving, so nothing on screen can be trusted and rule 4
 * blocks acting).
 *
 * The owner's decision (2026-09-28): the STANDBY pose plus a hollow ring,
 * the same on both apps, and TalkBack says [FaceWords.OFFLINE]. It replaced
 * the old ladder - hold the face for 12 s, then the reversed ERROR motion,
 * then BANKED after three minutes, read out as "notes saved for later",
 * which was not true.
 *
 * The 12 s grace is kept, for the reason it was written: a dropped radio on
 * a train or a hand-over between cell towers is not Jarvis going away, and
 * the link bar already says "Reconnecting" in words. With one exception: an
 * approval face is never shown on a cut link, not even inside the grace -
 * the approval buttons are blocked the moment the link is cut
 * (`JarvisRuntime.decisionBlocker`, rule 4), and a face saying "waiting for
 * your decision" when no decision can be sent is a face that lies.
 */
object FaceLink {

    /**
     * How long a cut link may last before the face admits it. Long enough to
     * cover a hand-over between cell towers or a screen-off doze wake-up;
     * short enough that a PC that has actually gone away does not keep
     * pretending to think.
     */
    const val GRACE_MS = 12_000L

    data class Shown(val state: FaceState, val offline: Boolean)

    private val OFFLINE_SHOWN = Shown(FaceState.STANDBY, offline = true)

    /**
     * @param normal the face the runtime would show on a healthy link.
     * @param cutSinceMs when the link was cut (down or stale), or 0 while it
     *   is healthy.
     */
    fun shown(normal: FaceState, cutSinceMs: Long, nowMs: Long): Shown {
        if (cutSinceMs == 0L) return Shown(normal, offline = false)
        if (normal == FaceState.APPROVAL) return OFFLINE_SHOWN
        return if (nowMs - cutSinceMs >= GRACE_MS) OFFLINE_SHOWN else Shown(normal, offline = false)
    }

    /**
     * How long until [shown] changes its answer by itself, in ms: the rest of
     * the grace, or 0 when nothing is pending. Never more than [GRACE_MS],
     * even if the wall clock was set backwards.
     */
    fun graceLeftMs(cutSinceMs: Long, nowMs: Long): Long {
        if (cutSinceMs == 0L) return 0L
        return (GRACE_MS - (nowMs - cutSinceMs)).coerceIn(0L, GRACE_MS)
    }
}

/**
 * Dimming a whole picture - an animal - the way every other face's colours
 * are dimmed: blended toward the ground by the state's `dim` (the shell's
 * transform table, [Spec.transformFor]: error 0.9, standby 0.6, banked 0.45),
 * never multiplied toward black. See FaceView's `dimmed` for why a multiply
 * would make banked vanish on an OLED panel.
 *
 * The other faces are drawn from two colours, so dimming the two colours
 * dims the face. An animal's fur and feathers keep their own colours
 * (CritterFaces), so dimming only the orb and rim left a standby panda at
 * 0.99 of its idle brightness while Arc sat at 0.41. The animal is dimmed as
 * a picture instead: every pixel becomes `mix(ground, pixel, dim)`.
 */
object DimRule {

    /**
     * The 4x5 colour matrix (`android.graphics.ColorMatrix` layout, offsets
     * in 0..255) for `mix(ground, pixel, dim)` on each colour channel, alpha
     * untouched; or null at full brightness, when no filter should be set.
     *
     * Android applies a matrix colour filter to UNpremultiplied colour, so
     * the soft, part-transparent outline blends correctly too: composited
     * over the ground, a pixel of coverage `a` ends as
     * `ground * (1 - a * dim) + dim * colour * a` - exactly the dimmed
     * version of what it would have been.
     *
     * @param r ground's red, 0..1 (sRGB, as Compose's `Color.red`); g, b alike.
     */
    fun matrix(dim: Float, r: Float, g: Float, b: Float): FloatArray? {
        if (dim.isNaN() || dim >= 1f) return null
        val k = dim.coerceIn(0f, 1f)
        val off = (1f - k) * 255f
        return floatArrayOf(
            k, 0f, 0f, 0f, off * r,
            0f, k, 0f, 0f, off * g,
            0f, 0f, k, 0f, off * b,
            0f, 0f, 0f, 1f, 0f,
        )
    }

    /**
     * What [matrix] does to one colour (0..1 channels, unpremultiplied), for
     * the tests: the same arithmetic the colour filter runs per pixel.
     */
    fun applyTo(m: FloatArray, rgba: FloatArray): FloatArray = FloatArray(4) { row ->
        val o = row * 5
        (m[o] * rgba[0] + m[o + 1] * rgba[1] + m[o + 2] * rgba[2] + m[o + 3] * rgba[3] + m[o + 4] / 255f)
            .coerceIn(0f, 1f)
    }
}

/**
 * Keeping the face's clocks small (FaceHost).
 *
 * A 32-bit float has 24 bits of precision. The host's clocks used to be
 * float accumulators that only ever grew, so after about 18 hours on screen
 * (2^16 s) each 1/60 s frame was being added in steps of 1/128 s - motion
 * jittered - and after a few days a frame's time rounded to nothing and the
 * face froze. Now each clock is accumulated in a Double (no drift) and
 * wrapped back toward zero, so the Float handed to the draw stays precise.
 *
 * Where a wrap can be seen. The animals are built for it: everything in their
 * poses repeats every [CritterPose.PERIOD] seconds (4096, "an app may restart
 * its clock at any multiple of PERIOD") - so the clocks wrap by whole
 * multiples of it and an animal never jumps. The approval knock (1.6 s)
 * divides it too. For the other faces, and the colour patterns, a wrap can
 * skip some sub-motions to another phase in one frame - so the wrap is done
 * when the face was NOT on screen, whenever it can be: each time the frame
 * loop starts again (screen back on, app back in front), once a clock has
 * passed [SOFT_S]. Only a face left on screen without a break for [HARD_S]
 * (about 9 hours) wraps while being watched, once, at that point.
 *
 * The spin angles wrap by whole multiples of [ANGLE_WRAP] = 2 pi x 1280, a
 * whole number of turns - and 1280 is a multiple of 20, so the faces that
 * turn at 0.3, 0.35, 1.1, 1.8 or 2.4 times the angle also land on whole
 * turns.
 */
object FaceClock {

    /** The wrap unit for the time clocks: the animals' own PERIOD. */
    const val WRAP_S: Double = CritterPose.PERIOD.toDouble()

    /** Wrapped when the frame loop restarts (unseen) past this. */
    const val SOFT_S: Double = WRAP_S

    /** Wrapped regardless, on screen, past this: 2^15 s, float step 1/256 s. */
    const val HARD_S: Double = WRAP_S * 8.0

    /** The wrap unit for the spin angles: 1280 whole turns. */
    const val ANGLE_WRAP: Double = 2.0 * PI * 1280.0

    /** Wrapped when the loop restarts past this... */
    const val ANGLE_SOFT: Double = ANGLE_WRAP

    /** ...and regardless past this (about 32,000 rad, float step 1/256 rad). */
    const val ANGLE_HARD: Double = ANGLE_WRAP * 4.0

    /**
     * How much to take off [x] to bring it into 0 until [unit]: a whole
     * multiple of [unit], so anything periodic in [unit] is unchanged. 0
     * when [x] is under [threshold] in size (nothing to do yet).
     */
    fun excess(x: Double, unit: Double, threshold: Double): Double {
        if (!x.isFinite() || kotlin.math.abs(x) < threshold) return 0.0
        return unit * floor(x / unit)
    }
}
