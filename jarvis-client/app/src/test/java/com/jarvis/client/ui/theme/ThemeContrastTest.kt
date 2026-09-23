package com.jarvis.client.ui.theme

import androidx.compose.ui.graphics.Color
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

/**
 * The theme guarantees, checked instead of promised (the audit's custom-15).
 *
 * `Chrome.kt` said "[wellIsLegal] asserts it", but nothing ever read
 * `wellIsLegal`, and every contrast figure in `Themes.kt` was a comment. Glow,
 * the look presets and anything later that tints a surface are safe only
 * because the well stays near-black and the text tiers keep their measured
 * contrast - so a later "let's lighten this one shade" should fail here, not
 * on the owner's phone.
 *
 * "Worst" means what `Chrome.kt` says it means: the minimum across all three
 * surfaces, not just the darkest one.
 */
class ThemeContrastTest {

    private fun surfaces(c: Chrome): List<Color> = listOf(c.surface0, c.surface1, c.surface2)

    private fun worst(fg: Color, c: Chrome): Float = surfaces(c).minOf { contrastRatio(fg, it) }

    /**
     * A figure written to two decimals in a comment matches when it is within
     * rounding of the measured one. The extra 0.001 is float slack: the
     * comments were worked out in double precision, this runs in Float.
     */
    private fun assertClaim(what: String, claimed: Float, measured: Float) {
        assertEquals("$what: Themes.kt claims $claimed:1, measured $measured:1", claimed, measured, 0.006f)
    }

    @Test
    fun everyWellIsNearBlack() {
        for (t in Themes.ALL) {
            assertTrue("${t.id}: the well must stay near-black (Y <= 0.01)", t.wellIsLegal)
        }
    }

    /** So the test above is not passing because the check can never fail. */
    @Test
    fun aLightWellIsCaught() {
        assertFalse(Themes.REACTOR.copy(well = Color.White).wellIsLegal)
        assertFalse(Themes.DAYLIGHT.copy(well = Themes.DAYLIGHT.surface0).wellIsLegal)
    }

    @Test
    fun everyTextTierClearsAaOnEverySurface() {
        for (t in Themes.ALL) {
            for ((name, colour) in listOf("textHi" to t.textHi, "textMid" to t.textMid, "textLo" to t.textLo)) {
                val w = worst(colour, t)
                assertTrue("${t.id}.$name is $w:1 at worst, under WCAG AA's 4.5:1", w >= 4.5f)
            }
        }
    }

    @Test
    fun hairlineFocusClearsThreeToOneOnEverySurface() {
        for (t in Themes.ALL) {
            val w = worst(t.hairlineFocus, t)
            assertTrue("${t.id}.hairlineFocus is $w:1 at worst, under WCAG 1.4.11's 3:1", w >= 3.0f)
        }
    }

    /** Every "N:1 worst" figure written next to a colour in Themes.kt. */
    @Test
    fun theWrittenFiguresAreTheMeasuredOnes() {
        data class Claim(val theme: Chrome, val tier: String, val colour: Color, val figure: Float)

        val claims = listOf(
            Claim(Themes.REACTOR, "textHi", Themes.REACTOR.textHi, 14.32f),
            Claim(Themes.REACTOR, "textMid", Themes.REACTOR.textMid, 6.91f),
            Claim(Themes.REACTOR, "textLo", Themes.REACTOR.textLo, 4.57f),
            Claim(Themes.REACTOR, "hairlineFocus", Themes.REACTOR.hairlineFocus, 3.68f),

            Claim(Themes.VOID, "textHi", Themes.VOID.textHi, 15.93f),
            Claim(Themes.VOID, "textMid", Themes.VOID.textMid, 7.46f),
            Claim(Themes.VOID, "textLo", Themes.VOID.textLo, 4.57f),
            Claim(Themes.VOID, "hairlineFocus", Themes.VOID.hairlineFocus, 3.53f),

            Claim(Themes.GRAPHITE, "textHi", Themes.GRAPHITE.textHi, 13.18f),
            Claim(Themes.GRAPHITE, "textMid", Themes.GRAPHITE.textMid, 6.88f),
            Claim(Themes.GRAPHITE, "textLo", Themes.GRAPHITE.textLo, 4.76f),
            Claim(Themes.GRAPHITE, "hairlineFocus", Themes.GRAPHITE.hairlineFocus, 3.28f),

            Claim(Themes.EMBER_DUSK, "textHi", Themes.EMBER_DUSK.textHi, 14.99f),
            Claim(Themes.EMBER_DUSK, "textMid", Themes.EMBER_DUSK.textMid, 7.65f),
            Claim(Themes.EMBER_DUSK, "textLo", Themes.EMBER_DUSK.textLo, 4.76f),
            Claim(Themes.EMBER_DUSK, "hairlineFocus", Themes.EMBER_DUSK.hairlineFocus, 3.51f),

            Claim(Themes.DAYLIGHT, "textHi", Themes.DAYLIGHT.textHi, 15.88f),
            Claim(Themes.DAYLIGHT, "textMid", Themes.DAYLIGHT.textMid, 6.38f),
            Claim(Themes.DAYLIGHT, "textLo", Themes.DAYLIGHT.textLo, 4.95f),
            Claim(Themes.DAYLIGHT, "hairlineFocus", Themes.DAYLIGHT.hairlineFocus, 3.03f),

            Claim(Themes.CONTRAST, "textHi", Themes.CONTRAST.textHi, 19.80f),
            Claim(Themes.CONTRAST, "textMid", Themes.CONTRAST.textMid, 14.44f),
            Claim(Themes.CONTRAST, "hairline", Themes.CONTRAST.hairline, 4.50f),
            Claim(Themes.CONTRAST, "hairlineStrong", Themes.CONTRAST.hairlineStrong, 8.90f),
        )
        for (c in claims) {
            assertClaim("${c.theme.id}.${c.tier}", c.figure, worst(c.colour, c.theme))
        }
    }

    /** "a 'faint' tier is a contradiction in a high-contrast theme, so textLo aliases textMid". */
    @Test
    fun highContrastHasTwoTextTiers() {
        assertEquals(Themes.CONTRAST.textMid, Themes.CONTRAST.textLo)
    }

    /**
     * Daylight's two semantic tiers: step 1 for words ("9.70:1 at worst") and
     * step 2 for icons and fills ("4.39:1 at worst", which is why it is not
     * used for text, and still clears the 3:1 that non-text needs).
     */
    @Test
    fun daylightSemanticTiers() {
        val d = Themes.DAYLIGHT
        val ink = listOf(d.okInk, d.warnInk, d.badInk).minOf { worst(it, d) }
        val mark = listOf(d.okMark, d.warnMark, d.badMark).minOf { worst(it, d) }
        assertClaim("daylight ink tier", 9.70f, ink)
        assertClaim("daylight mark tier", 4.39f, mark)
        assertTrue("daylight marks must clear 3:1 for non-text", mark >= 3.0f)
    }

    /** Dark themes use step 4 for both tiers, and it must be readable as text. */
    @Test
    fun darkThemeSemanticInkClearsAa() {
        for (t in Themes.ALL.filter { it.dark }) {
            for ((name, colour) in listOf("okInk" to t.okInk, "warnInk" to t.warnInk, "badInk" to t.badInk)) {
                val w = worst(colour, t)
                assertTrue("${t.id}.$name is $w:1 at worst, under 4.5:1", w >= 4.5f)
            }
        }
    }

    /** Glow may only be turned DOWN by a theme. */
    @Test
    fun postScaleNeverBrightens() {
        for (t in Themes.ALL) {
            assertTrue("${t.id}.postScale is ${t.postScale}", t.postScale > 0f && t.postScale <= 1f)
        }
    }

    @Test
    fun themeIdsAreUniqueAndTheDefaultIsListed() {
        assertEquals(Themes.ALL.size, Themes.ALL.map { it.id }.toSet().size)
        assertTrue(Themes.DEFAULT in Themes.ALL)
        assertTrue("the default must be a dark theme", Themes.DEFAULT.dark)
    }
}
