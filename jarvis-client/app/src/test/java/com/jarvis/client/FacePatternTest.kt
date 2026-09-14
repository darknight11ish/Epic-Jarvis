package com.jarvis.client

import androidx.compose.ui.graphics.Color
import com.jarvis.client.face.Binding
import com.jarvis.client.face.Bindings
import com.jarvis.client.face.FlashGovernor
import com.jarvis.client.face.Palette
import com.jarvis.client.face.Params
import com.jarvis.client.face.Pattern
import com.jarvis.client.face.PatternKind
import com.jarvis.client.face.StrobeBudget
import com.jarvis.client.face.resolve
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
        val bound = Binding(Pattern.GRADIENT, Palette.ICE_4)
        for (i in 0..40) {
            val out = resolveRaw(bound, i * 0.25f, 0f)
            val hue = hueOf(out.a)
            // Ice is around 190 degrees. Magenta - the old default - is ~320.
            assertTrue("hue $hue drifted out of the bound colour's family", hue in 150f..230f)
        }
    }

    @Test
    fun `an unbound gradient uses the pattern's own two hues`() {
        // This test used to assert only that the result was not black, which it
        // passed while running ice-4 to ice-3 - the generic fallback, not the
        // pattern's azure-4 to magenta-4. Assert the hues the spec names.
        val unbound = Binding(Pattern.GRADIENT)
        var lowest = 360f
        var highest = 0f
        for (i in 0..280) {
            val hue = hueOf(resolveRaw(unbound, i * 0.05f, 0f).a)
            if (hue >= 0f) { lowest = min(lowest, hue); highest = max(highest, hue) }
        }
        // azure-4 is ~216 degrees, magenta-4 ~318. Ice would sit near 190 and
        // never reach 300.
        assertTrue("unbound gradient never reached magenta (top hue $highest)", highest > 300f)
        assertTrue("unbound gradient never reached azure (lowest hue $lowest)", lowest in 190f..230f)
    }

    @Test
    fun `rule one merges the pattern's params under the binding's`() {
        // sweep and rainbow are the same KIND and differ only in params. With
        // one generic default shared by every pattern, a bound sweep rendered as
        // a full rainbow: span fell back to 360 instead of the pattern's 90.
        assertEquals(90f, Binding(Pattern.SWEEP).merged.spanDeg)
        assertEquals(360f, Binding(Pattern.RAINBOW).merged.spanDeg)
        assertEquals(5f, Binding(Pattern.SWEEP).merged.periodS)
        assertEquals(6f, Binding(Pattern.RAINBOW).merged.periodS)
        // And an override still wins.
        assertEquals(2f, Binding(Pattern.SWEEP, params = Params(periodS = 2f)).merged.periodS)
        // while leaving its neighbours on the pattern's own values.
        assertEquals(90f, Binding(Pattern.SWEEP, params = Params(periodS = 2f)).merged.spanDeg)
    }

    @Test
    fun `standby breathes at the pattern's own period`() {
        // It was 11 seconds - the midpoint of randomise.timing.breathe.standby,
        // a rule for GENERATING bindings applied by mistake to a shipped one.
        // The desktop resolved 4.5 and the two clients rendered different greys.
        assertEquals(4.5f, Bindings.DEFAULTS.of(FaceState.STANDBY).merged.periodS)
    }

    @Test
    fun `a comet's tail is the pattern's colour, not a darkened head`() {
        // Derived from the head, the two collapsed to the same value at the loop
        // extreme and the comet had no visible tail at all.
        val comet = Binding(Pattern.COMET)
        assertEquals(Palette.ICE_1, comet.merged.tail)
        val head = resolveRaw(comet, 1.2f, 0f).a
        val tail = resolveRaw(comet, 0f, 0f).b
        assertTrue("head and tail collapsed to the same colour", relLuma(head) - relLuma(tail) > 0.05f)
    }

    @Test
    fun `a strobe stops itself after the spec's limit`() {
        // limits.flash.strobe_max_s. Nothing enforced it, and the state most
        // likely to strobe is error, which lasts until somebody fixes it.
        val strobe = Binding(Pattern.STROBE)
        val budget = StrobeBudget()
        val governor = FlashGovernor()
        var t = 0f
        var last = resolve(strobe, t, 0f, governor, budget)
        // Past the limit the output must stop changing.
        while (t < Spec.STROBE_MAX_S + 1f) { t += 0.1f; last = resolve(strobe, t, 0f, governor, budget) }
        val settled = last
        repeat(20) { t += 0.1f; last = resolve(strobe, t, 0f, governor, budget) }
        assertEquals("a spent strobe kept flashing", relLuma(settled.a), relLuma(last.a), 0.001f)
        assertTrue("a spent strobe froze on its dark phase", relLuma(last.a) > 0.05f)
    }

    @Test
    fun `flicker cannot be bound above the photosensitivity cap`() {
        val wild = Binding(Pattern.FLICKER, params = Params(rateHz = 40f))
        // Count opposing luminance transitions over four seconds. The cap exists
        // so the 2.3x harmonic lands just under three a second.
        var dir = 0
        var transitions = 0
        var prev = relLuma(resolveRaw(wild, 0f, 0f).a)
        for (i in 1..2400) {
            val t = i / 600f
            val y = relLuma(resolveRaw(wild, t, 0f).a)
            val d = y - prev
            if (abs(d) >= Spec.FLASH_MIN_LUMA_DELTA) {
                val nd = if (d > 0) 1 else -1
                if (nd != dir) { transitions++; dir = nd }
                prev = y
            }
        }
        assertTrue(
            "$transitions opposing transitions in 4s is over the limit",
            transitions <= Spec.FLASH_MAX_TRANSITIONS_PER_S * 4,
        )
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
