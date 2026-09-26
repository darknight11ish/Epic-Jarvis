package com.jarvis.client.ui.theme

import androidx.compose.ui.graphics.Color
import com.jarvis.client.face.Palette

/**
 * The three themes: one dark, one light, one for maximum legibility.
 *
 * There were six. Void, Graphite and Ember Dusk were cut at the owner's
 * request because on a phone they read as the same near-black - which they
 * nearly had to be, since the face needs a dark ground (Chrome.well) and
 * every dark theme's surfaces sat within a few shades of it. A phone that
 * saved one of them lands on Reactor through [byId].
 *
 * Every colour below was measured, not picked: each text tier clears its target
 * against the WORST of the three surfaces, not merely the darkest, and the
 * comments carry the tight numbers so a later "let's darken this one shade"
 * knows what it is spending.
 *
 * The semantic trio is step 4 in every dark theme, including Contrast. Raising
 * it to step 5 there is the obvious move and it is wrong: step 4 already clears
 * AAA at 8.43:1, and step 5 buys contrast nobody needed while collapsing
 * ok-versus-bad under deuteranopia from 8.2 to 4.6 — the exact figure the spec
 * already ruled unacceptable elsewhere. The mist tiers converge toward white,
 * and white has no hue to lose.
 */
object Themes {

    /**
     * The default. Cool near-black, the product's established look, reconciled
     * with the HUD's `--plate` and the spec's `renderer.background`.
     *
     * Tightest pair in the system: text-lo on surface-2 at 4.57:1, clearing AA
     * by 0.07. The HUD's own `#6b8496` sat at 3.5:1 there and failed; this is
     * the smallest change that clears it.
     */
    val REACTOR = Chrome(
        id = "reactor",
        label = "Reactor",
        blurb = "The default. Cool near-black, built around the reactor's own light.",
        dark = true,
        surface0 = Color(0xFF04070C),
        surface1 = Color(0xFF0A1119),
        surface2 = Color(0xFF0E1822),
        well = Color(0xFF04070C),
        textHi = Palette.NEUTRAL_5,   // 14.32:1 worst
        textMid = Palette.NEUTRAL_4,  // 6.91:1 worst
        textLo = Color(0xFF6E8397),   // 4.57:1 worst
        hairline = Color(0xFF172836),
        hairlineStrong = Color(0xFF24485E),
        hairlineFocus = Color(0xFF4E7690), // 3.68:1 worst
        okInk = Palette.VERDANT_4,
        warnInk = Palette.AMBER_4,
        badInk = Palette.ROSE_4,
        okMark = Palette.VERDANT_4,
        warnMark = Palette.AMBER_4,
        badMark = Palette.ROSE_4,
        cloudInk = Palette.VIOLET_4, // 6.04:1 worst, 5.03:1 in a Pill
    )

    /**
     * Light chrome with the reactor in a dark inset well — a dark gauge face in
     * a light dashboard, which is what real instruments do.
     *
     * Deliberately NOT "light mode", and the distinction is honest rather than
     * pedantic. A fully light theme is not buildable here: every face composites
     * additively (`globalCompositeOperation 'lighter'`, and the bloom sprite
     * too), and a light source on a white page is not dim, it is nothing. The
     * reactor would be a white disc on a white card. Converting to source-over
     * would mean rewriting twenty faces and would still lose the glow, which is
     * the product.
     *
     * So the well stays dark, and this theme earns its place on the text
     * screens — the inbox, the approval cards, anything read outdoors.
     */
    val DAYLIGHT = Chrome(
        id = "daylight",
        label = "Daylight",
        blurb = "Light chrome for reading outdoors. The reactor keeps its dark well.",
        dark = false,
        surface0 = Color(0xFFEEF1F6),
        surface1 = Color(0xFFFFFFFF),
        surface2 = Color(0xFFE8EDF4),
        // Dark, on a light theme, on purpose. See the note above.
        well = Color(0xFF04070C),
        textHi = Color(0xFF0D1319),   // 15.88:1 worst
        textMid = Palette.NEUTRAL_3,  // 6.38:1 worst
        textLo = Color(0xFF54677C),   // 4.95:1 worst
        hairline = Color(0xFFC6D0DC),
        hairlineStrong = Color(0xFF98A6B6),
        hairlineFocus = Color(0xFF7C8998), // 3.03:1 worst — the tightest anywhere
        // Step 1 for words: 9.70:1 at worst, easily clearing AA.
        okInk = Palette.VERDANT_1,
        warnInk = Palette.AMBER_1,
        badInk = Palette.ROSE_1,
        // Step 2 for icons and fills: 4.39:1 at worst, which fails AA for text
        // and passes the 3:1 that non-text needs — and carries 9.8 ΔE of
        // ok/bad separation to a deuteranope against step 1's 7.5.
        okMark = Palette.VERDANT_2,
        warnMark = Palette.AMBER_2,
        badMark = Palette.ROSE_2,
        // Step 2 for the Cloud label. Violet-4, which most dark themes use,
        // is 2.52:1 here and 2.25:1 inside a Pill. Step 2 is still plainly
        // violet, where step 1 reads as near-black.
        cloudInk = Palette.VIOLET_2, // 8.66:1 worst, 6.90:1 in a Pill
    )

    /**
     * High contrast. Text and hairlines only.
     *
     * Two text tiers, not three: a "faint" tier is a contradiction in a
     * high-contrast theme, so textLo aliases textMid. Surfaces are flat and
     * depth comes from borders rather than tone.
     */
    val CONTRAST = Chrome(
        id = "contrast",
        label = "High Contrast",
        blurb = "Maximum legibility. Flat surfaces, strong borders, two text weights.",
        dark = true,
        surface0 = Color(0xFF000000),
        surface1 = Color(0xFF000000),
        surface2 = Color(0xFF0A0A0A),
        well = Color(0xFF000000),
        textHi = Color(0xFFFFFFFF),   // 19.80:1 worst
        textMid = Color(0xFFD5DDE6),  // 14.44:1 worst
        textLo = Color(0xFFD5DDE6),   // aliased, deliberately
        hairline = Color(0xFF6B7A8A),       // 4.50:1 — not decorative here
        hairlineStrong = Color(0xFF9FB0C0), // 8.90:1
        hairlineFocus = Color(0xFF9FB0C0),
        okInk = Palette.VERDANT_4,
        warnInk = Palette.AMBER_4,
        badInk = Palette.ROSE_4,
        okMark = Palette.VERDANT_4,
        warnMark = Palette.AMBER_4,
        badMark = Palette.ROSE_4,
        cloudInk = Palette.VIOLET_4, // 6.67:1 worst, 5.75:1 in a Pill
    )

    val ALL: List<Chrome> = listOf(REACTOR, DAYLIGHT, CONTRAST)

    val DEFAULT: Chrome = REACTOR

    fun byId(id: String?): Chrome = ALL.firstOrNull { it.id == id } ?: DEFAULT

    /** The theme a "follow the system" setting maps to for each OS mode. */
    fun forSystem(systemDark: Boolean, preferredDark: Chrome): Chrome =
        if (systemDark) preferredDark else DAYLIGHT
}
