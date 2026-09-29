package com.jarvis.client.face

import kotlin.math.floor
import kotlin.math.max
import kotlin.math.pow

/*
 * The two still rings the app draws round a face - plain Kotlin, no Compose,
 * so a JVM test can hold them to the desktop's numbers (faces.html
 * `drawOfflineRing` / `drawErrorRing`, and the golden fixture
 * jarvis-desktop/tests/fixtures/ring-cases.json that both sides are checked
 * against). FaceView draws them.
 *
 *   Not connected: a COMPLETE circle, the heavier of the two, in the standby
 *                  state's colour.
 *   Error:         a THIN arc with a 70 degree GAP centred at the BOTTOM
 *                  (six o'clock), in the error colour, on the four animals
 *                  and the robot (owner, 2026-09-29).
 *
 * Both are static - no pulse, no fade - so both are fine under Still, calm
 * motion and a serious moment. They are told apart by shape (a gap or none,
 * heavy or thin), not by colour alone, and neither is the waiting-on-you
 * clock: that one is drawn inside them (0.95 of the overlay radius against
 * their 1.03), starts at twelve o'clock, sweeps, and is never shown while
 * the face is not connected.
 */
object FaceRings {

    /** Both rings' radius, as a share of the overlay radius (0.44 of the box). */
    const val RING_R = 1.03f

    /** The not-connected ring's line: a share of the box, and its floor in px. Heavy. */
    const val OFFLINE_W = 0.012f
    const val OFFLINE_MIN_PX = 2.5f

    /** The error ring's line: a share of the box, and its floor in px. Thin. */
    const val ERROR_W = 0.006f
    const val ERROR_MIN_PX = 1.5f

    /** The error ring's gap, in degrees, centred at six o'clock. */
    const val ERROR_GAP_DEG = 70f

    /** Compose's arc angles: 0 is three o'clock and they grow clockwise, so 90 is six o'clock. */
    const val SIX_OCLOCK_DEG = 90f

    /** Where the error arc starts (just after the gap) and how far it sweeps round to just before it. */
    fun errorArcStart(): Float = SIX_OCLOCK_DEG + ERROR_GAP_DEG / 2f
    fun errorArcSweep(): Float = 360f - ERROR_GAP_DEG

    // --- readable against the ground --------------------------------------
    //
    // Leave the colour alone when it already measures LO..HI : 1 (WCAG)
    // against the ground; otherwise move it toward white or black (too
    // faint: to about BOOST : 1) or back toward the ground (too loud: to
    // about TEMPER : 1). The not-connected ring used to be dimmed by
    // standby's 0.6 and measured 1.65 : 1, which made "cannot hear me" and
    // "asleep" look alike from across a room.

    const val LO = 3.2
    const val HI = 5.5
    const val BOOST = 4.0
    const val TEMPER = 5.0

    /** WCAG relative luminance of an sRGB colour (channels 0..255). */
    fun luminance(c: IntArray): Double {
        fun f(v: Int): Double {
            val s = v / 255.0
            return if (s <= 0.03928) s / 12.92 else ((s + 0.055) / 1.055).pow(2.4)
        }
        return 0.2126 * f(c[0]) + 0.7152 * f(c[1]) + 0.0722 * f(c[2])
    }

    /** WCAG contrast ratio, 1..21. */
    fun contrast(a: IntArray, b: IntArray): Double {
        val la = luminance(a)
        val lb = luminance(b)
        return (max(la, lb) + 0.05) / (minOf(la, lb) + 0.05)
    }

    /** Round half up, as JavaScript's Math.round does - the desktop's numbers must match. */
    private fun round(x: Double): Int = floor(x + 0.5).toInt()

    private fun mixTo(from: IntArray, to: IntArray, t: Double): IntArray =
        IntArray(3) { round(from[it] + (to[it] - from[it]) * t) }

    /** The ring colour for [c] on the ground [bg] (each `[r, g, b]`, 0..255). The desktop's `ringTone`. */
    fun tone(c: IntArray, bg: IntArray): IntArray {
        val k = contrast(c, bg)
        if (k in LO..HI) return c.copyOf()
        if (k > HI) {
            // Too loud: back toward the ground, from the colour itself.
            for (i in 512 downTo 0) {
                val m = mixTo(bg, c, i / 512.0)
                if (contrast(m, bg) <= TEMPER) return m
            }
            return c.copyOf()
        }
        // Too faint: toward whichever of white and black stands out more.
        val far = if (luminance(bg) > 0.179) intArrayOf(0, 0, 0) else intArrayOf(255, 255, 255)
        for (i in 0..512) {
            val m = mixTo(c, far, i / 512.0)
            if (contrast(m, bg) >= BOOST) return m
        }
        return far
    }
}
