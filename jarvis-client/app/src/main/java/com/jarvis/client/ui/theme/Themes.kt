package com.jarvis.client.ui.theme

import androidx.compose.ui.graphics.Color
import com.jarvis.client.face.Palette

/**
 * The six themes.
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
     * True black. On an OLED panel those pixels are genuinely off — less power,
     * and the edge of the app disappears into the bezel.
     *
     * This is the theme where `dim_rule`'s "blend toward the background, never
     * multiply toward zero" earns its keep: a multiply would land banked around
     * 0.002 relative luminance, which many OLED panels quantise to black, and a
     * banked face that renders as nothing is a notification that did not happen.
     */
    val VOID = Chrome(
        id = "void",
        label = "Void",
        blurb = "True black. Saves power on an OLED screen and hides the app's edges.",
        dark = true,
        surface0 = Color(0xFF000000),
        surface1 = Color(0xFF070A0F),
        surface2 = Color(0xFF0D131B),
        well = Color(0xFF000000),
        textHi = Color(0xFFE6EEF7),   // 15.93:1 worst
        textMid = Color(0xFF93A6BA),  // 7.46:1 worst
        textLo = Color(0xFF6C8093),   // 4.57:1 worst
        hairline = Color(0xFF16202B),
        hairlineStrong = Color(0xFF26384A),
        hairlineFocus = Color(0xFF4B7088), // 3.53:1 worst
        okInk = Palette.VERDANT_4,
        warnInk = Palette.AMBER_4,
        badInk = Palette.ROSE_4,
        okMark = Palette.VERDANT_4,
        warnMark = Palette.AMBER_4,
        badMark = Palette.ROSE_4,
        cloudInk = Palette.VIOLET_4, // 6.28:1 worst, 5.26:1 in a Pill
    )

    /**
     * Lifted neutral ground, no hue in the chrome at all, and a well DARKER
     * than the surfaces — so the reactor reads as a light source sitting in a
     * recess rather than a sticker on a panel.
     *
     * Its restraint is in the glow budget too, not only the tokens: postScale
     * 0.5 halves the bloom.
     */
    val GRAPHITE = Chrome(
        id = "graphite",
        label = "Graphite",
        blurb = "Restrained. No colour in the chrome, and a quieter glow.",
        dark = true,
        surface0 = Color(0xFF101317),
        surface1 = Color(0xFF171B21),
        surface2 = Color(0xFF1E242B),
        well = Color(0xFF0B0D10),
        textHi = Color(0xFFE8ECF1),   // 13.18:1 worst
        textMid = Color(0xFFA3ADB9),  // 6.88:1 worst
        textLo = Color(0xFF848F9C),   // 4.76:1 worst
        hairline = Color(0xFF2B323A),
        hairlineStrong = Color(0xFF3D4650),
        hairlineFocus = Color(0xFF69747F), // 3.28:1 worst
        okInk = Palette.VERDANT_4,
        warnInk = Palette.AMBER_4,
        badInk = Palette.ROSE_4,
        okMark = Palette.VERDANT_4,
        warnMark = Palette.AMBER_4,
        badMark = Palette.ROSE_4,
        // Step 5, not 4: violet-4 is 5.27:1 as plain text on this lifted
        // ground but 4.35:1 inside a Pill, which fails AA.
        cloudInk = Palette.VIOLET_5, // 9.63:1 worst, 7.13:1 in a Pill
        postScale = 0.5f,
    )

    /**
     * Warm dark, low blue, for the evening.
     *
     * This is the theme that proves the architecture: it changes the ground's
     * hue and touches not one state colour. The chrome goes warm; the face
     * stays exactly as bound. The trio stays at step 4 — cool greens on a warm
     * ground is a contrast, not a clash, and dropping it to reduce blue light
     * would cost separation the warm chrome has already delivered.
     */
    val EMBER_DUSK = Chrome(
        id = "ember_dusk",
        label = "Ember Dusk",
        blurb = "Warm and low-blue, for the evening. The face is unchanged.",
        dark = true,
        surface0 = Color(0xFF0B0805),
        surface1 = Color(0xFF140F0A),
        surface2 = Color(0xFF1D150E),
        well = Color(0xFF0B0805),
        textHi = Color(0xFFF2E9DD),   // 14.99:1 worst
        textMid = Color(0xFFB5A794),  // 7.65:1 worst
        textLo = Color(0xFF8F8172),   // 4.76:1 worst
        hairline = Color(0xFF2E2318),
        hairlineStrong = Color(0xFF46341F),
        hairlineFocus = Color(0xFF806A50), // 3.51:1 worst
        okInk = Palette.VERDANT_4,
        warnInk = Palette.AMBER_4,
        badInk = Palette.ROSE_4,
        okMark = Palette.VERDANT_4,
        warnMark = Palette.AMBER_4,
        badMark = Palette.ROSE_4,
        cloudInk = Palette.VIOLET_4, // 6.07:1 worst, 5.08:1 in a Pill
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

    val ALL: List<Chrome> = listOf(REACTOR, VOID, GRAPHITE, EMBER_DUSK, DAYLIGHT, CONTRAST)

    val DEFAULT: Chrome = REACTOR

    fun byId(id: String?): Chrome = ALL.firstOrNull { it.id == id } ?: DEFAULT

    /** The theme a "follow the system" setting maps to for each OS mode. */
    fun forSystem(systemDark: Boolean, preferredDark: Chrome): Chrome =
        if (systemDark) preferredDark else DAYLIGHT
}
