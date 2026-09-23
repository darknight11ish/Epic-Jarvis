package com.jarvis.client.ui.theme

import android.provider.Settings
import androidx.compose.foundation.isSystemInDarkTheme
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.LocalContentColor
import androidx.compose.material3.LocalTextStyle
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Typography
import androidx.compose.material3.darkColorScheme
import androidx.compose.material3.lightColorScheme
import androidx.compose.runtime.Composable
import androidx.compose.runtime.CompositionLocalProvider
import androidx.compose.runtime.Immutable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.ProvidableCompositionLocal
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.runtime.staticCompositionLocalOf
import androidx.compose.runtime.withFrameNanos
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.Shape
import androidx.compose.ui.graphics.lerp
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.platform.LocalDensity
import androidx.compose.ui.text.TextStyle
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.Density
import androidx.compose.ui.unit.Dp
import androidx.compose.ui.unit.TextUnit
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.em
import androidx.compose.ui.unit.sp
import androidx.compose.animation.core.CubicBezierEasing
import androidx.compose.animation.core.Easing
import androidx.compose.animation.core.FiniteAnimationSpec
import androidx.compose.animation.core.tween

/**
 * The theme's colours, everywhere.
 *
 * `staticCompositionLocalOf`, not `compositionLocalOf`, and the reason is
 * counter-intuitive enough to record. The tracking kind recomposes only actual
 * readers, which sounds better — but it adds a lookup at every one of the
 * hundred-odd read sites, on every frame, for ever. The static kind costs
 * nothing to read and instead restarts the whole subtree when the value
 * changes. A theme switch happens once, on a deliberate tap. Paying for
 * recomposition then, to pay nothing on the other 99.99% of frames, is the
 * right way round — especially with a 60fps canvas on the same thread.
 *
 * Since the theme crossfade (see [JarvisTheme]) "then" is 500ms of frames, not
 * one: the value changes on every frame of the fade. That is still the right
 * trade - half a second of extra work after a deliberate tap, rate-limited by
 * the store's dwell - and it is skipped entirely under reduced motion.
 */
val LocalChrome: ProvidableCompositionLocal<Chrome> =
    staticCompositionLocalOf { Themes.DEFAULT }

/**
 * The accent, derived from the idle binding rather than chosen by the theme.
 *
 * Provided here so call sites read one value instead of recomputing a family
 * walk. See [accentFor] for why it is a function of the bindings.
 */
val LocalAccent: ProvidableCompositionLocal<Color> =
    staticCompositionLocalOf { Themes.DEFAULT.textHi }

val LocalRadii: ProvidableCompositionLocal<Radii> = staticCompositionLocalOf { Radii() }

val LocalMotion: ProvidableCompositionLocal<Motion> = staticCompositionLocalOf { Motion() }

/** Comfortable or Compact padding. See [Spacing]. */
val LocalSpacing: ProvidableCompositionLocal<Spacing> = staticCompositionLocalOf { Spacing() }

/** How a [com.jarvis.client.ui.parts.Plate] marks its edge. See [PlateEdges]. */
val LocalPlateEdges: ProvidableCompositionLocal<PlateEdges> =
    staticCompositionLocalOf { PlateEdges.HAIRLINE }

/**
 * Whether moving between screens should animate (fade and slide) or cut.
 *
 * Already false whenever the phone asks for reduced motion, so a caller reads
 * this one value and never has to combine it with [Motion.reduced] itself.
 * Nothing in the theme reads it: it is here for the navigation host, which
 * owns the screen changes.
 */
val LocalTransitions: ProvidableCompositionLocal<Boolean> = staticCompositionLocalOf { true }

/**
 * Density: how much air there is inside plates and between blocks.
 *
 * Only padding and gaps shrink. Touch targets do not: every control in
 * `Parts.kt` keeps its 48dp minimum in Compact too, because a smaller target
 * is an accessibility regression, not a density choice.
 */
@Immutable
data class Spacing(val compact: Boolean = false) {
    /** Inside a plate: 14dp, or 10dp compact. */
    val plate: Dp get() = if (compact) 10.dp else 14.dp

    /** The vertical padding of one label/value row. */
    val field: Dp get() = if (compact) 3.dp else 5.dp

    /**
     * A vertical gap of [dp], scaled by two thirds when compact (12 -> 8,
     * 8 -> 5.3). Scaled rather than looked up, so every existing `Gap(n)`
     * call site tightens in proportion without being rewritten.
     */
    fun gap(dp: Int): Dp = if (compact) (dp * COMPACT_GAP).dp else dp.dp

    private companion object {
        const val COMPACT_GAP = 2f / 3f
    }
}

/**
 * How a plate's edge is drawn. Appearance → "Panel edges".
 *
 * None of these is a shadow: shadows are banned for their per-frame cost (see
 * Plate). High Contrast keeps a strong border under every option, because its
 * plates are the same colour as the page and would otherwise have no edge.
 */
enum class PlateEdges {
    /** A 1dp line in `hairline` all round. The default. */
    HAIRLINE,

    /** The hairline, plus a 1dp lighter line just inside the top edge. */
    BEVEL,

    /** Tone only: the plate differs from the page by colour and nothing else. */
    NONE,
}

/**
 * A named scale rather than eight loose literals.
 *
 * Shares the desktop's *scale*, not its numbers: 18px on a 640px floating pane
 * and 18dp on a 400dp phone are different proportions of their container.
 */
@Immutable
data class Radii(
    val shell: Dp = 18.dp,
    val card: Dp = 14.dp,
    val control: Dp = 10.dp,
    val inset: Dp = 8.dp,
) {
    val shellShape: Shape get() = RoundedCornerShape(shell)
    val cardShape: Shape get() = RoundedCornerShape(card)
    val controlShape: Shape get() = RoundedCornerShape(control)
    val insetShape: Shape get() = RoundedCornerShape(inset)

    /**
     * The fully-round pill. It is the "this is a label, not a control" shape
     * signal, and the phone had no such shape at all while the desktop used it
     * for route badges, note chips, approval targets and digest kinds.
     */
    val chipShape: Shape get() = RoundedCornerShape(percent = 50)

    companion object {
        /**
         * Appearance → "Shape: Sharp". Small radii rather than zero: a square
         * corner at phone scale reads as unfinished rather than as precise.
         * The pill ([chipShape]) stays round on purpose - it is the shape that
         * says "label, not control", and that signal must not change with taste.
         */
        val SHARP = Radii(shell = 6.dp, card = 4.dp, control = 4.dp, inset = 2.dp)
    }
}

/**
 * One easing curve and three durations, instead of whatever Compose defaults
 * to at each call site.
 *
 * The curve is the desktop's `cubic-bezier(0.22, 1, 0.36, 1)` exactly. The
 * durations are shorter than the desktop's, on purpose and by a documented
 * factor: touch wants a faster acknowledgement than a pointer does.
 */
@Immutable
data class Motion(
    val ease: Easing = JarvisEase,
    /** A press, a ripple-replacement, a chip toggling. */
    val microMs: Int = 120,
    /** Something appearing or leaving. */
    val enterMs: Int = 200,
    /** A state changing under you — the link, the face, a theme. */
    val stateMs: Int = 280,
    /**
     * True when the OS animation scale is zero.
     *
     * The desktop honours `prefers-reduced-motion` on all three of its
     * surfaces; the phone honoured it on none, which is the worse gap, because
     * the phone is where the most motion-heavy thing in the product lives.
     * Every duration here collapses to zero when this is set. The face's own
     * motion is handled separately — see FaceView — because a face frozen
     * entirely would stop reporting state at all.
     */
    val reduced: Boolean = false,
) {
    private fun d(ms: Int) = if (reduced) 0 else ms

    fun <T> micro(): FiniteAnimationSpec<T> = tween(d(microMs), easing = ease)
    fun <T> enter(): FiniteAnimationSpec<T> = tween(d(enterMs), easing = ease)
    fun <T> state(): FiniteAnimationSpec<T> = tween(d(stateMs), easing = ease)
}

/** The desktop's one easing token, ported exactly. */
val JarvisEase: Easing = CubicBezierEasing(0.22f, 1f, 0.36f, 1f)

/**
 * The type scale.
 *
 * Sizes are resolved for a phone rather than copied from the desktop: 14px at
 * 60cm on a monitor and 14sp at 30cm in a hand are not the same apparent size,
 * and matching the numbers would make the phone read small. The *relationships*
 * are shared — the weight and tracking of a kicker against a body line.
 *
 * Body is 17sp, not Material's 14. This is a thing you read at arm's length
 * with one hand, often outdoors.
 *
 * TODO: the product's own face is IBM Plex Sans, bundled on the desktop under
 * the OFL. It is not bundled here — no font CDN is reachable from this build
 * environment — so this rides the platform font at the right weights and
 * tracking. Dropping the TTFs into res/font/ and pointing [sans] at them is the
 * only change needed.
 */
object JarvisType {

    val sans: FontFamily = FontFamily.Default

    /** For machine-authored strings only: ids, hashes, paths, model names. */
    val mono: FontFamily = FontFamily.Monospace

    val typography: Typography = Typography().let { base ->
        Typography(
            displaySmall = TextStyle(
                fontFamily = sans, fontWeight = FontWeight.Light,
                fontSize = 34.sp, lineHeight = 40.sp, letterSpacing = (-0.02).em,
            ),
            headlineSmall = TextStyle(
                fontFamily = sans, fontWeight = FontWeight.Medium,
                fontSize = 22.sp, lineHeight = 28.sp, letterSpacing = (-0.01).em,
            ),
            // Pairing's wordmark asks for titleLarge, and this ramp used to leave
            // it out - so the one screen a new owner sees first fell through to
            // Material's own default instead of this scale. Same size as
            // Material's, in this ramp's family and tracking.
            titleLarge = TextStyle(
                fontFamily = sans, fontWeight = FontWeight.SemiBold,
                fontSize = 22.sp, lineHeight = 28.sp, letterSpacing = (-0.005).em,
            ),
            titleMedium = TextStyle(
                fontFamily = sans, fontWeight = FontWeight.SemiBold,
                fontSize = 18.sp, lineHeight = 24.sp,
            ),
            titleSmall = TextStyle(
                fontFamily = sans, fontWeight = FontWeight.SemiBold,
                fontSize = 16.sp, lineHeight = 22.sp,
            ),
            bodyLarge = TextStyle(
                fontFamily = sans, fontWeight = FontWeight.Normal,
                fontSize = 17.sp, lineHeight = 25.sp,
            ),
            bodyMedium = TextStyle(
                fontFamily = sans, fontWeight = FontWeight.Normal,
                fontSize = 15.sp, lineHeight = 22.sp,
            ),
            bodySmall = TextStyle(
                fontFamily = sans, fontWeight = FontWeight.Normal,
                fontSize = 13.sp, lineHeight = 19.sp,
            ),
            labelLarge = TextStyle(
                fontFamily = sans, fontWeight = FontWeight.Medium,
                fontSize = 15.sp, lineHeight = 20.sp,
            ),
            labelMedium = TextStyle(
                fontFamily = sans, fontWeight = FontWeight.Medium,
                fontSize = 13.sp, lineHeight = 17.sp,
            ),
            // The kicker. Uppercase, tracked out — the desktop's 10-11.5px at
            // 600-650 weight with 0.4-0.7px of letter-spacing. Without the
            // tracking, uppercase at this size reads as shouting rather than as
            // a label.
            labelSmall = TextStyle(
                fontFamily = sans, fontWeight = FontWeight.SemiBold,
                fontSize = 11.sp, lineHeight = 15.sp, letterSpacing = 0.09.em,
            ),
        )
    }

    /** For ids, hashes and model names. Never for prose. */
    val machine: TextStyle = TextStyle(
        fontFamily = mono, fontWeight = FontWeight.Normal,
        fontSize = 13.sp, lineHeight = 18.sp,
    )

    /**
     * Short instrument readouts: ON/OFF inside a Toggle, counts, countdowns.
     * The phone's own monospace (no bundled font - the owner chose to keep the
     * built-in ones), small, medium weight and tracked out like a kicker, so a
     * two-letter word still reads as a label. Write the text in capitals at
     * the call site; the style does not uppercase it.
     */
    val telemetry: TextStyle = TextStyle(
        fontFamily = mono, fontWeight = FontWeight.Medium,
        fontSize = 11.sp, lineHeight = 14.sp, letterSpacing = 0.06.em,
    )
}

/**
 * Wraps the app once.
 *
 * Every parameter after [idleColor] is an Appearance choice that changes only
 * how this phone looks, and each has a default equal to how the app looked
 * before the choice existed - so a call that passes none of them gets exactly
 * the old app (plus plate edges, which are the new default look).
 *
 * @param chrome the theme's colours.
 * @param idleColor the colour bound to the idle state, from which the accent is
 *   derived. Passing the *binding* rather than an accent is what stops the
 *   chrome and the face ever disagreeing.
 * @param compact Density: Compact tightens padding and gaps. See [Spacing].
 * @param sharp Shape: small corner radii instead of rounded. See [Radii.SHARP].
 * @param textScale Text size, as a multiplier ON TOP of the phone's own font
 *   size setting: 1f (the default) means "follow the phone" and leaves the
 *   phone's setting completely untouched. 0 or less also means "follow the
 *   phone", so a store that uses 0 for that works too. Other values are held
 *   to [MIN_TEXT_SCALE]..[MAX_TEXT_SCALE].
 * @param edges Panel edges. See [PlateEdges].
 * @param transitions Screen transitions on or off. Provided as
 *   [LocalTransitions], already forced off under reduced motion.
 */
@Composable
fun JarvisTheme(
    chrome: Chrome,
    idleColor: Color,
    compact: Boolean = false,
    sharp: Boolean = false,
    textScale: Float = 1f,
    edges: PlateEdges = PlateEdges.HAIRLINE,
    transitions: Boolean = true,
    content: @Composable () -> Unit,
) {
    val context = LocalContext.current
    val reduced = remember(context) {
        runCatching {
            Settings.Global.getFloat(
                context.contentResolver,
                Settings.Global.ANIMATOR_DURATION_SCALE,
                1f,
            ) == 0f
        }.getOrDefault(false)
    }

    // The theme crossfade. `AppearanceStore` and MainActivity both describe
    // a 500ms crossfade as half of the photosensitivity reasoning ("500ms
    // crossfade plus 500ms dwell"), and until now it did not exist: a theme
    // change was a one-frame cut, Void to Daylight being black to near-white
    // in 16ms. The dwell alone still kept the flash RATE legal; the fade makes
    // each step a ramp instead of a jump, which is what the comments promised.
    //
    // The colours are faded, not the content. A `Crossfade` over the whole
    // app would compose two copies of every screen for half a second - two
    // face canvases, two GL surfaces - where this recomposes one copy once a
    // frame. Every frame of the fade is ONE state write of an (origin, target, t)
    // triple, so no frame can ever see a new `target` paired with a stale `t` and
    // flash the target in early.
    //
    // Skipped under reduced motion, as the brief for this change asked: the
    // cut there is the same one the app has always made.
    var fade by remember { mutableStateOf(ThemeFade(chrome, chrome, 1f)) }
    LaunchedEffect(chrome, reduced) {
        if (fade.t >= 1f && fade.target == chrome) return@LaunchedEffect
        // Start from exactly what is on screen now, so a second change in the
        // middle of a fade turns smoothly instead of jumping back to a theme.
        val start = fade.shown()
        if (reduced) {
            fade = ThemeFade(chrome, chrome, 1f)
            return@LaunchedEffect
        }
        fade = ThemeFade(start, chrome, 0f)
        val t0 = withFrameNanos { it }
        while (true) {
            val now = withFrameNanos { it }
            val linear = ((now - t0) / 1_000_000f / THEME_FADE_MS).coerceIn(0f, 1f)
            if (linear >= 1f) break
            fade = ThemeFade(start, chrome, JarvisEase.transform(linear))
        }
        // Lands on the caller's own instance, not an interpolated copy, so
        // anything that compares `LocalChrome.current` with a theme sees it.
        fade = ThemeFade(chrome, chrome, 1f)
    }
    val shown = fade.shown()

    // The accent is derived from each END of the fade and the two are mixed,
    // rather than derived from the half-way colours: `accentFor` walks the
    // palette in whole steps, and running it on a mid-fade surface would make
    // the accent hop between steps during the fade.
    val toAccent = remember(fade.target, idleColor) { accentFor(fade.target, idleColor) }
    val fromAccent = remember(fade.origin, idleColor) { accentFor(fade.origin, idleColor) }
    val accent = if (fade.t >= 1f) toAccent else lerp(fromAccent, toAccent, fade.t)
    val motion = remember(reduced) { Motion(reduced = reduced) }
    val spacing = remember(compact) { Spacing(compact = compact) }
    val radii = if (sharp) Radii.SHARP else DEFAULT_RADII

    // Text size rides on the font scale, which is exactly what the phone's
    // own setting changes, so every `sp` in the app follows with no call site
    // touched. Multiplied, not replaced: the owner's phone-wide choice is kept.
    // At 1f the phone's own Density object is passed through untouched - that
    // matters, because on Android 14+ it scales large text NON-linearly (so
    // 200% body text does not become 200% headlines), and a Density built
    // here is linear. So only an explicit choice pays that difference.
    val baseDensity = LocalDensity.current
    val scale = if (textScale > 0f) textScale.coerceIn(MIN_TEXT_SCALE, MAX_TEXT_SCALE) else 1f
    val density = remember(baseDensity, scale) {
        if (scale == 1f) {
            baseDensity
        } else {
            Density(density = baseDensity.density, fontScale = baseDensity.fontScale * scale)
        }
    }

    // Material3's own scheme is filled in from the chrome so that any stock
    // component pulled in later lands on the right colours rather than on
    // baseline purple. The app's own surfaces read LocalChrome directly.
    val scheme = remember(shown, accent) {
        if (shown.dark) {
            darkColorScheme(
                primary = accent,
                onPrimary = shown.surface0,
                background = shown.surface0,
                onBackground = shown.textHi,
                surface = shown.surface1,
                onSurface = shown.textHi,
                surfaceVariant = shown.surface2,
                onSurfaceVariant = shown.textMid,
                outline = shown.hairlineFocus,
                outlineVariant = shown.hairline,
                error = shown.badInk,
            )
        } else {
            lightColorScheme(
                primary = accent,
                onPrimary = shown.surface1,
                background = shown.surface0,
                onBackground = shown.textHi,
                surface = shown.surface1,
                onSurface = shown.textHi,
                surfaceVariant = shown.surface2,
                onSurfaceVariant = shown.textMid,
                outline = shown.hairlineFocus,
                outlineVariant = shown.hairline,
                error = shown.badInk,
            )
        }
    }

    CompositionLocalProvider(
        LocalChrome provides shown,
        LocalAccent provides accent,
        LocalRadii provides radii,
        LocalMotion provides motion,
        LocalSpacing provides spacing,
        LocalPlateEdges provides edges,
        LocalTransitions provides (transitions && !reduced),
        LocalDensity provides density,
        LocalContentColor provides shown.textHi,
        LocalTextStyle provides JarvisType.typography.bodyLarge,
    ) {
        MaterialTheme(
            colorScheme = scheme,
            typography = JarvisType.typography,
            content = content,
        )
    }
}

/** The theme crossfade's length. The dwell in `AppearanceStore` assumes 500. */
const val THEME_FADE_MS = 500

/** The Text size setting's range: 90-130% in the plan, with a little slack. */
const val MIN_TEXT_SCALE = 0.85f
const val MAX_TEXT_SCALE = 1.5f

private val DEFAULT_RADII = Radii()

/**
 * One frame of the theme crossfade: [t] of the way from [origin] to [target].
 * Held as one value so a frame can never pair a new [target] with an old [t].
 */
@Immutable
private data class ThemeFade(val origin: Chrome, val target: Chrome, val t: Float) {
    fun shown(): Chrome = if (t >= 1f || origin == target) target else mixChrome(origin, target, t)
}

/**
 * [from] and [to] mixed [t] of the way. Colours and the glow budget blend;
 * identity (id, label, blurb) and `dark` are the target's from the first
 * frame, so the Appearance picker marks the new theme the moment it is tapped.
 */
private fun mixChrome(from: Chrome, to: Chrome, t: Float): Chrome = to.copy(
    surface0 = lerp(from.surface0, to.surface0, t),
    surface1 = lerp(from.surface1, to.surface1, t),
    surface2 = lerp(from.surface2, to.surface2, t),
    well = lerp(from.well, to.well, t),
    textHi = lerp(from.textHi, to.textHi, t),
    textMid = lerp(from.textMid, to.textMid, t),
    textLo = lerp(from.textLo, to.textLo, t),
    hairline = lerp(from.hairline, to.hairline, t),
    hairlineStrong = lerp(from.hairlineStrong, to.hairlineStrong, t),
    hairlineFocus = lerp(from.hairlineFocus, to.hairlineFocus, t),
    okInk = lerp(from.okInk, to.okInk, t),
    warnInk = lerp(from.warnInk, to.warnInk, t),
    badInk = lerp(from.badInk, to.badInk, t),
    okMark = lerp(from.okMark, to.okMark, t),
    warnMark = lerp(from.warnMark, to.warnMark, t),
    badMark = lerp(from.badMark, to.badMark, t),
    cloudInk = lerp(from.cloudInk, to.cloudInk, t),
    postScale = from.postScale + (to.postScale - from.postScale) * t,
)

/** Whether the OS is in dark mode, for the "follow the system" setting. */
@Composable
fun systemPrefersDark(): Boolean = isSystemInDarkTheme()
