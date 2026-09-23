package com.jarvis.client.ui.theme

import androidx.compose.runtime.Immutable
import androidx.compose.ui.graphics.Color
import com.jarvis.client.face.Palette

/**
 * A theme's colours — the parts of the interface that say nothing about what
 * Jarvis is doing.
 *
 * The split this class encodes is the whole theme design, so it is worth
 * stating plainly. Every colour in the app falls into one of three classes, and
 * the class decides who owns it:
 *
 * **Class A — theme-owned, free.** Surfaces, text tiers, hairlines, scrim.
 * Nothing here is ever read by the face or compared with the desktop.
 *
 * **Class B — theme-owned, constrained.** `ok`, `warn`, `bad`. A theme picks
 * the *step*, never the *family*: verdant, amber, rose. Those are the families
 * `randomise.state_rules` pins approval and error to, and it refuses to move
 * them — "a green alarm is a design you have to explain". Letting a theme
 * choose the family would let a theme break a rule the randomiser is forbidden
 * to break.
 *
 * **Class C — not theme-owned at all.** Every state colour, and the chrome
 * accent. Those come from `resolve()` and from [accentFor], which derives the
 * accent from the *idle binding*. There is deliberately no accent token here
 * and no accent picker: press Randomise, and the caret, the focus ring and the
 * selected tab follow the face, on both clients, because the chrome has no
 * opinion of its own.
 *
 * Every contrast figure in the tables below is measured against WCAG 2.x
 * relative luminance, and `worst` means the minimum across all three surfaces —
 * not just the darkest one, which is how a text tier ends up failing on exactly
 * one card.
 */
@Immutable
data class Chrome(
    val id: String,
    val label: String,
    /** One line for the picker. Says what it is for, not what it looks like. */
    val blurb: String,
    val dark: Boolean,

    // Class A ------------------------------------------------------------
    val surface0: Color,
    val surface1: Color,
    val surface2: Color,

    /**
     * The reactor's ground, and the ONE theme token the face is allowed to read.
     *
     * `renderer.background_why` pins a single ground for all faces because each
     * face used to paint its own and "showed as a differently tinted rectangle
     * in every gallery". The intent is cross-face consistency, not that one hex
     * — so a theme may choose it, but it applies to every face identically.
     *
     * It must stay dark. Faces composite additively, and `dim_rule` blends
     * *toward* this colour rather than multiplying toward zero, so a light well
     * both erases the glow and makes standby and banked dim toward white, where
     * they read as "disabled" instead of "waiting". Daylight keeps a dark inset
     * well for exactly this reason. [wellIsLegal] asserts it.
     */
    val well: Color,

    val textHi: Color,
    val textMid: Color,
    val textLo: Color,

    /** Decorative. Measures 1.2–2.0:1 and that is correct — see [hairlineFocus]. */
    val hairline: Color,
    val hairlineStrong: Color,

    /**
     * For anything that is the SOLE indicator of a control's boundary, focus or
     * selection: a focus ring, a selected chip, an input border, a switch track.
     * WCAG 1.4.11 wants 3:1 for those and every value here clears it.
     *
     * Not interchangeable with [hairlineStrong], which is half its contrast.
     * The names sound alike and the values do not; reaching for the wrong one is
     * the single most likely accessibility regression in this file.
     */
    val hairlineFocus: Color,

    // Class B ------------------------------------------------------------
    /** Semantic colours for TEXT. On dark themes these are step 4. */
    val okInk: Color,
    val warnInk: Color,
    val badInk: Color,

    /**
     * Semantic colours for ICONS AND FILLS, where the bar is 3:1 rather than
     * 4.5:1.
     *
     * Two tiers exist for the light theme's sake and are not a flourish. On
     * white, step 2 has the better hue separation (ok/bad 9.8 ΔE to a
     * deuteranope against step 1's 7.5) but amber-2 only reaches 4.39:1, which
     * fails AA for text. Step 1 clears text contrast easily and its separation
     * collapses to 7.9. So hue carries the mark tier, where 3:1 is the
     * requirement, and words carry the ink tier, where a label is present and
     * hue was never doing the distinguishing.
     *
     * On dark themes both tiers are the same step 4 colour.
     */
    val okMark: Color,
    val warnMark: Color,
    val badMark: Color,

    /**
     * The words that say "this is leaving your machine": the Cloud route
     * label on Home and on Mind.
     *
     * Class B in spirit, like `ok`/`warn`/`bad`: the family is fixed - violet
     * is the desktop's `--cloud` and means the same thing on both clients -
     * and a theme picks only the step. It used to be the one colour hardcoded
     * outside the theme (violet-4 at both call sites), which is fine on a dark
     * ground and 2.3:1 on Daylight - the fact that matters most for privacy,
     * least readable on the theme meant for reading outdoors.
     *
     * Every value clears 4.5:1 against all three surfaces AND inside a
     * [com.jarvis.client.ui.parts.Pill], whose ground is this same colour at
     * 13% over the surface, which costs up to a whole point of contrast.
     */
    val cloudInk: Color = Palette.VIOLET_4,

    /**
     * Multiplier on the glow's intensity, 0..1. A renderer setting rather than a
     * colour, so a restrained theme can be restrained without touching the
     * palette.
     */
    val postScale: Float = 1f,
) {
    /**
     * The well must stay essentially black.
     *
     * Not a style rule. Faces draw additively; on a ground above roughly
     * Y = 0.01 the glow saturates and the reactor is not dim, it is absent.
     */
    val wellIsLegal: Boolean get() = relativeLuminance(well) <= 0.01f
}

/** WCAG 2.x relative luminance. */
fun relativeLuminance(c: Color): Float {
    fun ch(v: Float) = if (v <= 0.03928f) v / 12.92f else Math.pow(
        ((v + 0.055f) / 1.055f).toDouble(), 2.4,
    ).toFloat()
    return 0.2126f * ch(c.red) + 0.7152f * ch(c.green) + 0.0722f * ch(c.blue)
}

/** WCAG 2.x contrast ratio, 1..21. */
fun contrastRatio(a: Color, b: Color): Float {
    val ya = relativeLuminance(a)
    val yb = relativeLuminance(b)
    val hi = maxOf(ya, yb)
    val lo = minOf(ya, yb)
    return (hi + 0.05f) / (lo + 0.05f)
}

/**
 * The chrome accent: the idle state's bound colour, walked along its OWN family
 * until it is legible on this theme's cards.
 *
 * This is the load-bearing idea of the whole theme system. The accent is not a
 * token a theme chooses — it is a function of the bindings — so a theme can
 * never disagree with the face about what colour Jarvis is. Re-roll idle to
 * violet and the caret, the focus ring and the streaming hairline all become
 * violet, on the phone and on the desktop, because both compute the same
 * function from the same bindings. (The focus ring is the 2dp border
 * `TextInput` draws while it has focus; the streaming hairline is still
 * HomeScreen's to draw.)
 *
 * The walk stays inside the family. Walking toward white would desaturate the
 * hue, and the hue is the thing the user bound; walking a step keeps it
 * recognisably the same colour and lands on a value the spec already sanctions.
 *
 * @param floor the contrast the accent must clear against [Chrome.surface1].
 */
fun accentFor(chrome: Chrome, bound: Color, floor: Float = 4.5f): Color {
    val family = Palette.familyOf(bound) ?: return fallbackAccent(chrome, bound, floor)
    val steps = Palette.steps(family)
    if (steps.isEmpty()) return bound
    val start = (Palette.stepOf(bound) ?: 4) - 1
    // Dark chrome walks toward the pale end, light chrome toward the deep end.
    val order = if (chrome.dark) {
        (start until steps.size) + (start - 1 downTo 0)
    } else {
        (start downTo 0) + (start + 1 until steps.size)
    }
    for (i in order) {
        val candidate = steps[i]
        if (contrastRatio(candidate, chrome.surface1) >= floor) return candidate
    }
    // Nothing in the family clears it. Take the best available rather than
    // something from outside the family: a slightly dim accent of the right hue
    // beats a legible one of the wrong hue.
    return steps.maxByOrNull { contrastRatio(it, chrome.surface1) } ?: bound
}

/**
 * For a colour that is not in the palette at all — which a hand-edited binding
 * could be. Nudges toward the text colour until it is legible.
 */
private fun fallbackAccent(chrome: Chrome, bound: Color, floor: Float): Color {
    var out = bound
    val toward = if (chrome.dark) Color.White else Color.Black
    var k = 0f
    while (k <= 1f) {
        out = Color(
            red = bound.red + (toward.red - bound.red) * k,
            green = bound.green + (toward.green - bound.green) * k,
            blue = bound.blue + (toward.blue - bound.blue) * k,
        )
        if (contrastRatio(out, chrome.surface1) >= floor) return out
        k += 0.05f
    }
    return out
}
