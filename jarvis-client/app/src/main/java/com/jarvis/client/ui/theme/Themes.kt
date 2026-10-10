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

// GENERATED - DO NOT EDIT. `tools/tokens/build.mjs` writes the three
// `Chrome(...)` blocks below from `tokens/themes.tokens.json`, and writes the
// desktop's `theme.css` from the same tokens. A colour that differs from the
// desktop's carries its reason in the token file, because a difference is a
// decision and never an accident. Change the token file, then run:
//
//     node tools/tokens/build.mjs

object Themes {

    val REACTOR = Chrome(
        id = "reactor",
        label = "Reactor",
        blurb = "The default. Cool near-black, built around the reactor's own light.",
        dark = true,

        // Class A ------------------------------------------------------------
        surface0 = Color(0xFF04070C),   // differs from the desktop; the token file says why
        surface1 = Color(0xFF0A1119),   // differs from the desktop; the token file says why
        surface2 = Color(0xFF0E1822),   // differs from the desktop; the token file says why
        well = Color(0xFF04070C),   // the face's ground; must stay essentially black (wellIsLegal)
        textHi = Palette.NEUTRAL_5,   // differs from the desktop; the token file says why
        textMid = Palette.NEUTRAL_4,   // differs from the desktop; the token file says why
        textLo = Color(0xFF6E8397),   // differs from the desktop; the token file says why
        hairline = Color(0xFF172836),   // differs from the desktop; the token file says why
        hairlineStrong = Color(0xFF24485E),   // differs from the desktop; the token file says why
        hairlineFocus = Color(0xFF4E7690),   // differs from the desktop; the token file says why

        // Class B ------------------------------------------------------------
        okInk = Palette.VERDANT_4,   // differs from the desktop; the token file says why
        warnInk = Palette.AMBER_4,   // differs from the desktop; the token file says why
        badInk = Palette.ROSE_4,   // differs from the desktop; the token file says why
        okMark = Palette.VERDANT_4,
        warnMark = Palette.AMBER_4,
        badMark = Palette.ROSE_4,

        // Class B in spirit: the words that say "this is leaving your machine".
        cloudInk = Palette.VIOLET_4,   // differs from the desktop; the token file says why
    )

    val DAYLIGHT = Chrome(
        id = "daylight",
        label = "Daylight",
        blurb = "Light chrome for reading outdoors. The reactor keeps its dark well.",
        dark = false,

        // Class A ------------------------------------------------------------
        surface0 = Color(0xFFEEF1F6),   // differs from the desktop; the token file says why
        surface1 = Color(0xFFFFFFFF),
        surface2 = Color(0xFFE8EDF4),   // differs from the desktop; the token file says why
        well = Color(0xFF04070C),   // the face's ground; must stay essentially black (wellIsLegal)
        textHi = Color(0xFF0D1319),   // differs from the desktop; the token file says why
        textMid = Palette.NEUTRAL_3,   // differs from the desktop; the token file says why
        textLo = Color(0xFF54677C),   // differs from the desktop; the token file says why
        hairline = Color(0xFFC6D0DC),   // differs from the desktop; the token file says why
        hairlineStrong = Color(0xFF98A6B6),   // differs from the desktop; the token file says why
        hairlineFocus = Color(0xFF7C8998),   // differs from the desktop; the token file says why

        // Class B ------------------------------------------------------------
        okInk = Palette.VERDANT_1,   // differs from the desktop; the token file says why
        warnInk = Palette.AMBER_1,   // differs from the desktop; the token file says why
        badInk = Palette.ROSE_1,   // differs from the desktop; the token file says why
        okMark = Palette.VERDANT_2,   // differs from the desktop; the token file says why
        warnMark = Palette.AMBER_2,   // differs from the desktop; the token file says why
        badMark = Palette.ROSE_2,   // differs from the desktop; the token file says why

        // Class B in spirit: the words that say "this is leaving your machine".
        cloudInk = Palette.VIOLET_2,   // differs from the desktop; the token file says why
    )

    val CONTRAST = Chrome(
        id = "contrast",
        label = "High Contrast",
        blurb = "Maximum legibility. Flat surfaces, strong borders, two text weights.",
        dark = true,

        // Class A ------------------------------------------------------------
        surface0 = Color(0xFF000000),
        surface1 = Color(0xFF000000),   // differs from the desktop; the token file says why
        surface2 = Color(0xFF0A0A0A),   // differs from the desktop; the token file says why
        well = Color(0xFF000000),   // the face's ground; must stay essentially black (wellIsLegal)
        textHi = Color(0xFFFFFFFF),
        textMid = Color(0xFFD5DDE6),   // differs from the desktop; the token file says why
        textLo = Color(0xFFD5DDE6),   // differs from the desktop; the token file says why
        hairline = Color(0xFF6B7A8A),   // differs from the desktop; the token file says why
        hairlineStrong = Color(0xFF9FB0C0),   // differs from the desktop; the token file says why
        hairlineFocus = Color(0xFF9FB0C0),   // differs from the desktop; the token file says why

        // Class B ------------------------------------------------------------
        okInk = Palette.VERDANT_4,   // differs from the desktop; the token file says why
        warnInk = Palette.AMBER_4,   // differs from the desktop; the token file says why
        badInk = Palette.ROSE_4,   // differs from the desktop; the token file says why
        okMark = Palette.VERDANT_4,
        warnMark = Palette.AMBER_4,
        badMark = Palette.ROSE_4,

        // Class B in spirit: the words that say "this is leaving your machine".
        cloudInk = Palette.VIOLET_4,   // differs from the desktop; the token file says why
    )

    val ALL: List<Chrome> = listOf(REACTOR, DAYLIGHT, CONTRAST)

    val DEFAULT: Chrome = REACTOR

    fun byId(id: String?): Chrome = ALL.firstOrNull { it.id == id } ?: DEFAULT

    /** The theme a "follow the system" setting maps to for each OS mode. */
    fun forSystem(systemDark: Boolean, preferredDark: Chrome): Chrome =
        if (systemDark) preferredDark else DAYLIGHT
}
