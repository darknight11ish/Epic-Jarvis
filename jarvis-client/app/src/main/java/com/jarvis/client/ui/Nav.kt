package com.jarvis.client.ui

import androidx.activity.compose.BackHandler
import androidx.compose.runtime.Composable
import androidx.compose.runtime.Stable
import androidx.compose.runtime.mutableStateListOf
import androidx.compose.runtime.saveable.listSaver
import androidx.compose.runtime.saveable.rememberSaveable

/**
 * The screens.
 *
 * `CHECKS` is reachable from everywhere including the pairing screen, which is
 * the fix for the one that mattered: the readiness checks used to be rendered
 * only inside the `link == CONNECTED` branch, so the screen that tells you why
 * you cannot connect was hidden exactly when you could not connect.
 */
enum class Screen { HOME, BRAIN, INBOX, CHECKS, APPEARANCE, FAQ }

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

    fun go(screen: Screen) {
        if (stack.last() == screen) return
        // Never stack the same screen twice: tapping Inbox from the inbox
        // should do nothing, not add a second copy to go back through.
        stack.remove(screen)
        stack.add(screen)
    }

    fun back(): Boolean {
        if (!canGoBack) return false
        stack.removeAt(stack.lastIndex)
        return true
    }

    /** Drops everything but home. Used when the app is re-entered from a notification. */
    fun resetTo(screen: Screen) {
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
 */
@Composable
fun NavBackHandler(nav: NavState) {
    BackHandler(enabled = nav.canGoBack) { nav.back() }
}
