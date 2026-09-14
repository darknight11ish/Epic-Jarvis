package com.jarvis.client

import androidx.compose.ui.graphics.Color
import com.jarvis.client.face.Binding
import com.jarvis.client.face.Bindings
import com.jarvis.client.face.FlashGovernor
import com.jarvis.client.face.PatternKind
import com.jarvis.client.face.Spec
import com.jarvis.client.face.Swatch
import com.jarvis.client.face.relLuma
import com.jarvis.client.face.resolveRaw
import com.jarvis.client.face.smooth
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNotEquals
import org.junit.Assert.assertTrue
import org.junit.Test
import kotlin.math.abs
import kotlin.math.max
import kotlin.math.min

/**
 * The pattern engine, and the three rules in it that are correctness rather
 * than taste.
 */
class FacePatternTest {

    private fun hueOf(c: Color): Float {
        val r = c.red; val g = c.green; val b = c.blue
        val mx = max(r, max(g, b)); val mn = min(r, min(g, b))
        val d = mx - mn
        if (d < 1e-6f) return -1f
        val h = when (mx) {
            r -> 60f * (((g - b) / d) % 6f)
            g -> 60f * (((b - r) / d) + 2f)
            else -> 60f * (((r - g) / d) + 4f)
        }
        return (h + 360f) % 360f
    }

    @Test
    fun `a bound colour beats the gradient pattern's own`() {
        // Nineteen of twenty speaking faces rendered pink because the pattern's
        // two-hue default won over the bound ice. A bound colour with no
        // explicit `to` must run between itself and its own darker step.
        val bound = Binding(PatternKind.GRADIENT, Spec.ICE_4)
        for (i in 0..40) {
            val out = resolveRaw(bound, i * 0.25f, 0f)
            val hue = hueOf(out.a)
            // Ice is around 190 degrees. Magenta - the old default - is ~320.
            assertTrue("hue $hue drifted out of the bound colour's family", hue in 150f..230f)
        }
    }

    @Test
    fun `an unbound gradient may use its own two hues`() {
        val unbound = Binding(PatternKind.GRADIENT, null)
        val out = resolveRaw(unbound, 0f, 0f)
        assertNotEquals(0f, out.a.red + out.a.green + out.a.blue)
    }

    @Test
    fun `thinking never lands on idle's cyan`() {
        // The first replacement for the rainbow bottomed out on cyan, which is
        // idle's hue, so a thinking face caught at that phase read as idle. The
        // band now starts above ice.
        val thinking = Bindings.DEFAULTS.of(FaceState.THINKING)
        var lowest = 360f
        for (i in 0..600) {
            val hue = hueOf(resolveRaw(thinking, i * 0.05f, 0f).a)
            if (hue >= 0f) lowest = min(lowest, hue)
        }
        assertTrue("thinking reached hue $lowest, which is idle's territory", lowest > 200f)
    }

    @Test
    fun `error pulses on rose and never leaves it`() {
        // It used to strobe to near-black, so any glance on the off phase saw
        // nothing and read as crashed.
        val error = Bindings.DEFAULTS.of(FaceState.ERROR)
        for (i in 0..400) {
            val out = resolveRaw(error, i * 0.01f, 0f)
            assertTrue("error went dark at t=${i * 0.01f}", relLuma(out.a) > 0.02f)
            val hue = hueOf(out.a)
            if (hue >= 0f) assertTrue("error drifted to hue $hue", hue < 30f || hue > 330f)
        }
    }

    @Test
    fun `the flash governor holds the colour once the budget is spent`() {
        val g = FlashGovernor()
        val bright = Swatch(Color.White, Color.White)
        val dark = Swatch(Color.Black, Color.Black)

        // Four opposing transitions inside one second. The fourth must be
        // refused - and refused by HOLDING what was already on screen, not by
        // passing through the colour being rejected.
        var t = 0f
        val seen = mutableListOf<Swatch>()
        repeat(8) { i ->
            t += 0.05f
            seen += g.govern(if (i % 2 == 0) bright else dark, t)
        }
        val distinct = seen.map { relLuma(it.a) }.distinct()
        assertTrue("the governor let every flash through", distinct.size <= 2)
        val transitions = seen.zipWithNext().count {
            abs(relLuma(it.first.a) - relLuma(it.second.a)) >= Spec.FLASH_MIN_LUMA_DELTA
        }
        assertTrue("$transitions transitions in 0.4s exceeds the limit", transitions <= 3)
    }

    @Test
    fun `each surface gets its own governor`() {
        // A single page-wide window fed by every surface in turn saw twenty
        // faces with twenty clocks as one face flashing between twenty colours.
        val a = FlashGovernor()
        val b = FlashGovernor()
        val bright = Swatch(Color.White, Color.White)
        val dark = Swatch(Color.Black, Color.Black)
        repeat(6) { i ->
            a.govern(if (i % 2 == 0) bright else dark, i * 0.05f)
        }
        // b has spent nothing, so it still passes its first transition through.
        b.govern(dark, 0f)
        assertEquals(relLuma(bright.a), relLuma(b.govern(bright, 0.05f).a), 0.001f)
    }

    @Test
    fun `smoothing is in seconds, so the refresh rate does not change the feel`() {
        // A fixed per-frame lerp smooths twice as fast at 120Hz as at 60Hz, and
        // the feel of the thing changed with the panel.
        fun run(dt: Float, steps: Int): Float {
            var v = 0f
            repeat(steps) { v = smooth(v, 1f, dt, Spec.MIC_ATTACK_S, Spec.MIC_RELEASE_S) }
            return v
        }
        val at60 = run(1f / 60f, 60)
        val at120 = run(1f / 120f, 120)
        assertEquals("one second of attack should land in the same place", at60, at120, 0.02f)
    }

    @Test
    fun `the borrowed states are the ones the spec names`() {
        assertEquals(FaceState.IDLE, Spec.transformFor(FaceState.APPROVAL).borrow)
        assertEquals(FaceState.THINKING, Spec.transformFor(FaceState.ERROR).borrow)
        assertEquals(FaceState.IDLE, Spec.transformFor(FaceState.STANDBY).borrow)
        assertEquals(FaceState.IDLE, Spec.transformFor(FaceState.BANKED).borrow)

        // Error is the only thing in this product that runs backwards, and that
        // direction is the signal - it survives colour blindness, a still frame
        // and peripheral vision.
        assertEquals(-1, Spec.transformFor(FaceState.ERROR).dir)
        assertEquals(1, Spec.transformFor(FaceState.APPROVAL).dir)

        // Banked is still, not slow.
        assertEquals(0f, Spec.transformFor(FaceState.BANKED).rate, 0f)
    }

    @Test
    fun `resting states draw at the reduced rates`() {
        assertEquals(30, Spec.fpsFor(FaceState.IDLE))
        assertEquals(15, Spec.fpsFor(FaceState.STANDBY))
        assertEquals(2, Spec.fpsFor(FaceState.BANKED))
        // Active states are untouched: 0 means "whatever the display gives us".
        assertEquals(0, Spec.fpsFor(FaceState.SPEAKING))
        assertEquals(0, Spec.fpsFor(FaceState.THINKING))
    }
}
