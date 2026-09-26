package com.jarvis.client.ui

import androidx.activity.BackEventCompat
import androidx.activity.compose.PredictiveBackHandler
import androidx.compose.animation.AnimatedContent
import androidx.compose.animation.EnterTransition
import androidx.compose.animation.ExitTransition
import androidx.compose.animation.core.tween
import androidx.compose.animation.fadeIn
import androidx.compose.animation.fadeOut
import androidx.compose.animation.slideInVertically
import androidx.compose.animation.togetherWith
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.Stable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableFloatStateOf
import androidx.compose.runtime.mutableIntStateOf
import androidx.compose.runtime.mutableStateListOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.saveable.listSaver
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.draw.drawBehind
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.StrokeCap
import androidx.compose.ui.graphics.drawscope.rotate
import androidx.compose.ui.graphics.graphicsLayer
import androidx.compose.ui.platform.LocalDensity
import androidx.compose.ui.unit.Dp
import androidx.compose.ui.unit.IntOffset
import androidx.compose.ui.unit.dp
import com.jarvis.client.ui.parts.pressable
import com.jarvis.client.ui.theme.LocalAccent
import com.jarvis.client.ui.theme.LocalChrome
import com.jarvis.client.ui.theme.LocalMotion
import com.jarvis.client.ui.theme.LocalRadii
import kotlinx.coroutines.CancellationException

/**
 * The screens.
 *
 * `CHECKS` is reachable from everywhere including the pairing screen, which is
 * the fix for the one that mattered: the readiness checks used to be rendered
 * only inside the `link == CONNECTED` branch, so the screen that tells you why
 * you cannot connect was hidden exactly when you could not connect.
 *
 * `VOICE` is "Train my voice", opened from the voice card on `CHECKS`. Added
 * last so a saved back stack from an older build still restores by name.
 *
 * `SECURITY` is the lock and fingerprint settings, opened from the Security
 * card on `CHECKS`. Last, for the same reason.
 *
 * `VOICE_CHECK` (how strict the voice check is, private answers, the repeat
 * test) and `VOICES` (custom voices) are opened from the voice card on
 * `CHECKS`. `HISTORY` is chat history on the PC (docs/JARVIS-API.md
 * section 18), opened from Mind. Last again, for the same reason.
 *
 * `SETTINGS` (ease-of-use audit 2026-09-27, row 16) is the phone's own
 * Settings screen: voice, security and appearance are only linked from it
 * (their own screens above are unchanged), while the small settings that
 * used to sit under Brain's "Settings" group render there directly. Reachable
 * from Brain and from `CHECKS`, and - like `CHECKS`, `FAQ` and `SECURITY` -
 * exempt from the pairing screen taking over, so it stays reachable mid-pair.
 * Last, for the same reason as the others above.
 */
enum class Screen {
    HOME, BRAIN, INBOX, CHECKS, APPEARANCE, FAQ, VOICE, SECURITY, VOICE_CHECK, VOICES, HISTORY, SETTINGS
}

/**
 * A back stack, because there was not one.
 *
 * The old shell was a `when {}` over three booleans with no `BackHandler`
 * anywhere in the codebase: system back from the inbox left the app instead of
 * returning to home, which on a phone is the single most-used control there is.
 *
 * `rememberSaveable`, so a rotation or a process death that Android restores
 * comes back on the screen you were on. Two of the old three flags were
 * saveable and `paired` was not, so a rotation on the readiness screen could
 * bounce you back to pairing with a paired device.
 *
 * A sealed hierarchy and a nav library would both be more machinery than five
 * destinations and one intent need.
 */
@Stable
class NavState internal constructor(initial: List<Screen>) {

    private val stack = mutableStateListOf<Screen>().also { it.addAll(initial) }

    val current: Screen get() = stack.last()

    val canGoBack: Boolean get() = stack.size > 1

    /**
     * How far a back swipe has travelled, 0..1, while the finger is still
     * down. Zero at every other time, including on phones older than
     * Android 14, which report no progress at all.
     *
     * Read by [NavScreens] in the draw phase only, so a swipe moves the
     * screen without recomposing it.
     */
    var backProgress: Float by mutableFloatStateOf(0f)
        internal set

    /** Which edge the swipe started from: [BackEventCompat.EDGE_LEFT] or EDGE_RIGHT. */
    internal var backEdge: Int by mutableIntStateOf(BackEventCompat.EDGE_LEFT)

    /**
     * True for the one screen change that a completed back SWIPE caused.
     *
     * The swipe has already shown the old screen shrinking away under the
     * finger, so fading it out again afterwards would play the same exit
     * twice. [NavScreens] drops the exit for that one change. Cleared by the
     * next ordinary move.
     */
    internal var backByGesture: Boolean by mutableStateOf(false)

    fun go(screen: Screen) {
        if (stack.last() == screen) return
        backByGesture = false
        // Never stack the same screen twice: tapping Inbox from the inbox
        // should do nothing, not add a second copy to go back through.
        stack.remove(screen)
        stack.add(screen)
    }

    fun back(): Boolean {
        if (!canGoBack) return false
        backByGesture = false
        stack.removeAt(stack.lastIndex)
        return true
    }

    /** Drops everything but home. Used when the app is re-entered from a notification. */
    fun resetTo(screen: Screen) {
        backByGesture = false
        stack.clear()
        stack.add(screen)
    }

    internal fun snapshot(): List<String> = stack.map { it.name }

    companion object {
        val Saver = listSaver<NavState, String>(
            save = { it.snapshot() },
            restore = { names ->
                val screens = names.mapNotNull { name ->
                    runCatching { Screen.valueOf(name) }.getOrNull()
                }
                NavState(screens.ifEmpty { listOf(Screen.HOME) })
            },
        )
    }
}

@Composable
fun rememberNavState(start: Screen = Screen.HOME): NavState =
    rememberSaveable(saver = NavState.Saver) { NavState(listOf(start)) }

/**
 * Wires system back to the stack.
 *
 * Enabled only when there is somewhere to go, so back from home still leaves
 * the app — which is what a phone user expects and what a blanket handler
 * would have broken.
 *
 * A [PredictiveBackHandler] rather than a plain `BackHandler` (screens-13).
 * The manifest already asks Android 14+ for the back-swipe preview
 * (`enableOnBackInvokedCallback`), but a plain `BackHandler` only hears the
 * END of the gesture, so inside the app there was nothing to preview - the
 * preview worked only when leaving it. This one also hears the swipe as it
 * happens and records how far it has gone in [NavState.backProgress], which
 * [NavScreens] turns into the screen following the finger.
 *
 * Nothing else changes. The swipe still ends in the same `nav.back()`, only
 * once the owner lets go past the point of no return; a swipe let go early is
 * cancelled and the screen snaps back to full size. On phones before Android 14, and on
 * three-button navigation, there is no progress to hear: the flow simply
 * completes on the press and this behaves exactly like the old handler.
 */
@Composable
fun NavBackHandler(nav: NavState) {
    PredictiveBackHandler(enabled = nav.canGoBack) { progress ->
        try {
            progress.collect { event ->
                nav.backEdge = event.swipeEdge
                nav.backProgress = event.progress
            }
            // Only a swipe that actually showed progress skips the exit fade;
            // a button press or an old phone gets the normal transition.
            // Set after back(), which clears it, and before the next frame
            // reads it - both writes land in the same snapshot.
            val byGesture = nav.backProgress > 0f
            nav.back()
            nav.backByGesture = byGesture
            nav.backProgress = 0f
        } catch (e: CancellationException) {
            // The swipe was let go before the point of no return. Settle
            // back, and let the cancellation carry on up - swallowing it
            // would break the coroutine this runs in.
            nav.backProgress = 0f
            throw e
        }
    }
}

/**
 * The screen switcher, with the transition between screens (screens-13).
 *
 * Replaces MainActivity's plain `when (nav.current) { ... }`, which cut
 * instantly from one screen to the next. The call site becomes
 * `NavScreens(nav, transitions = ...) { screen -> when (screen) { ... } }` -
 * note `screen`, not `nav.current`: during the short fade both the old and
 * the new screen are on the glass, and each must draw itself, not whatever
 * is current.
 *
 * The transition: the new screen fades in while rising 8dp, and the old one
 * fades out, both on the theme's own `enter` duration and easing. It plays
 * once per screen change and never runs in between, so the face stays the
 * only thing that moves all the time (the 09-14 "one animated surface" rule).
 *
 * It switches off - an instant cut, exactly the old behaviour - when:
 * - [transitions] is false (the Appearance setting "Screen transitions"), or
 * - the phone asks for less motion ([com.jarvis.client.ui.theme.Motion.reduced]),
 *   whatever [transitions] says.
 * The back-swipe preview goes with it: with transitions off, the screen does
 * not follow the finger either.
 *
 * During a back swipe the screen being left shrinks a little, rounds its
 * corners and moves with the finger. What shows behind it is a plain `surface2` panel, not
 * the screen you are going back to: that screen is only composed once the
 * swipe is let go. Drawing it underneath would mean keeping two screens -
 * one of them possibly Home with the face - alive for every swipe.
 *
 * Known cost, not measured on a phone: GL faces (Tokamak, Membrane) draw on a
 * GLSurfaceView, which ignores fading. Leaving Home, the face stays solid for
 * the ~200ms fade and then disappears, rather than fading with the rest.
 */
@Composable
fun NavScreens(
    nav: NavState,
    modifier: Modifier = Modifier,
    transitions: Boolean = true,
    content: @Composable (Screen) -> Unit,
) {
    val motion = LocalMotion.current
    val animate = transitions && !motion.reduced
    val rise = with(LocalDensity.current) { 8.dp.roundToPx() }
    val chrome = LocalChrome.current
    val cornerPx = with(LocalDensity.current) { 18.dp.toPx() }
    val shiftPx = with(LocalDensity.current) { 24.dp.toPx() }

    AnimatedContent(
        targetState = nav.current,
        // surface2 behind the screens, not the window's own colour: it is
        // what shows around a screen while a back swipe shrinks it.
        modifier = modifier.fillMaxSize().background(chrome.surface2),
        transitionSpec = {
            when {
                !animate -> EnterTransition.None togetherWith ExitTransition.None
                nav.backByGesture ->
                    fadeIn(motion.enter()) togetherWith fadeOut(tween(durationMillis = 0))
                else ->
                    (fadeIn(motion.enter()) + slideInVertically(motion.enter<IntOffset>()) { rise }) togetherWith
                        fadeOut(motion.enter())
            }
        },
        label = "screen",
    ) { screen ->
        Box(
            Modifier
                .fillMaxSize()
                .graphicsLayer {
                    // Read here, in the layer, so the swipe redraws this one
                    // layer and recomposes nothing. Only the screen being
                    // left follows the finger.
                    val p = if (animate && screen == nav.current) nav.backProgress else 0f
                    if (p > 0f) {
                        val s = 1f - 0.1f * p
                        scaleX = s
                        scaleY = s
                        // With the finger: away from the edge the swipe
                        // started at, as the platform's own preview does.
                        val dir = if (nav.backEdge == BackEventCompat.EDGE_LEFT) 1f else -1f
                        translationX = dir * shiftPx * p
                        shape = RoundedCornerShape(cornerPx * p)
                        clip = true
                    } else {
                        scaleX = 1f
                        scaleY = 1f
                        translationX = 0f
                        clip = false
                    }
                },
        ) {
            content(screen)
        }
    }
}

/**
 * A drawn chevron - a "v", as two strokes with round ends.
 *
 * Drawn rather than typed, for the same reason as the nav icons
 * (ui/parts/NavIcons.kt, the 09-18 audit's choice A1): a typed arrow
 * is whatever the phone's font makes of it, and "←" sat next to Home's
 * drawn icons like it came from a different app. Points DOWN at
 * [rotation] 0; 90 points left, 180 up, 270 right.
 *
 * Lives here because both of its users are about moving between or
 * inside screens: [BackButton], and the FAQ's open/close mark. It has no
 * semantics of its own - its caller says in words what it means.
 */
@Composable
fun Chevron(
    tint: Color,
    modifier: Modifier = Modifier,
    rotation: Float = 0f,
    size: Dp = 16.dp,
) {
    Box(
        modifier
            .size(size)
            .drawBehind {
                val w = 1.75.dp.toPx()
                rotate(rotation) {
                    val a = Offset(this.size.width * 0.22f, this.size.height * 0.36f)
                    val tip = Offset(this.size.width * 0.5f, this.size.height * 0.66f)
                    val b = Offset(this.size.width * 0.78f, this.size.height * 0.36f)
                    drawLine(tint, a, tip, w, cap = StrokeCap.Round)
                    drawLine(tint, tip, b, w, cap = StrokeCap.Round)
                }
            },
    )
}

/**
 * The one Back control for every sub-screen's top bar (screens-15).
 *
 * A drawn left chevron and the word "Back", replacing `Quiet("← Back", ...)`.
 * The word stays: the owner is new to this, and a bare chevron is one more
 * symbol to learn. Same 48dp touch height and spring-press as every other
 * control, and no Material ripple. The word is what a screen reader reads, so
 * the chevron needs no description of its own.
 */
@Composable
fun BackButton(onBack: () -> Unit, modifier: Modifier = Modifier) {
    val accent = LocalAccent.current
    Row(
        modifier
            .heightIn(min = 48.dp)
            .clip(LocalRadii.current.insetShape)
            .pressable(onClick = onBack)
            .padding(start = 6.dp, end = 10.dp),
        verticalAlignment = Alignment.CenterVertically,
    ) {
        Chevron(tint = accent, rotation = 90f)
        Spacer(Modifier.width(4.dp))
        Text("Back", style = MaterialTheme.typography.labelMedium, color = accent)
    }
}
