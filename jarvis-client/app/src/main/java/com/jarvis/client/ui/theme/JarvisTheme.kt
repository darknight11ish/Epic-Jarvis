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
import androidx.compose.runtime.ProvidableCompositionLocal
import androidx.compose.runtime.remember
import androidx.compose.runtime.staticCompositionLocalOf
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.Shape
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.TextStyle
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextAlign
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
 * changes. A theme switch happens once, on a deliberate tap. Paying one
 * recomposition then, to pay nothing on the other 99.99% of frames, is the
 * right way round — especially with a 60fps canvas on the same thread.
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
}

/**
 * Wraps the app once.
 *
 * @param chrome the theme's colours.
 * @param idleColor the colour bound to the idle state, from which the accent is
 *   derived. Passing the *binding* rather than an accent is what stops the
 *   chrome and the face ever disagreeing.
 */
@Composable
fun JarvisTheme(
    chrome: Chrome,
    idleColor: Color,
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

    val accent = remember(chrome, idleColor) { accentFor(chrome, idleColor) }
    val motion = remember(reduced) { Motion(reduced = reduced) }

    // Material3's own scheme is filled in from the chrome so that any stock
    // component pulled in later lands on the right colours rather than on
    // baseline purple. The app's own surfaces read LocalChrome directly.
    val scheme = remember(chrome, accent) {
        if (chrome.dark) {
            darkColorScheme(
                primary = accent,
                onPrimary = chrome.surface0,
                background = chrome.surface0,
                onBackground = chrome.textHi,
                surface = chrome.surface1,
                onSurface = chrome.textHi,
                surfaceVariant = chrome.surface2,
                onSurfaceVariant = chrome.textMid,
                outline = chrome.hairlineFocus,
                outlineVariant = chrome.hairline,
                error = chrome.badInk,
            )
        } else {
            lightColorScheme(
                primary = accent,
                onPrimary = chrome.surface1,
                background = chrome.surface0,
                onBackground = chrome.textHi,
                surface = chrome.surface1,
                onSurface = chrome.textHi,
                surfaceVariant = chrome.surface2,
                onSurfaceVariant = chrome.textMid,
                outline = chrome.hairlineFocus,
                outlineVariant = chrome.hairline,
                error = chrome.badInk,
            )
        }
    }

    CompositionLocalProvider(
        LocalChrome provides chrome,
        LocalAccent provides accent,
        LocalRadii provides Radii(),
        LocalMotion provides motion,
        LocalContentColor provides chrome.textHi,
        LocalTextStyle provides JarvisType.typography.bodyLarge,
    ) {
        MaterialTheme(
            colorScheme = scheme,
            typography = JarvisType.typography,
            content = content,
        )
    }
}

/** Whether the OS is in dark mode, for the "follow the system" setting. */
@Composable
fun systemPrefersDark(): Boolean = isSystemInDarkTheme()
