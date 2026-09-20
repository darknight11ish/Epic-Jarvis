package com.jarvis.client.ui

import androidx.compose.runtime.Composable
import androidx.compose.ui.graphics.Color
import com.jarvis.client.ui.theme.LocalAccent
import com.jarvis.client.ui.theme.LocalChrome

/**
 * The old nine-colour token set, now reading from the live theme.
 *
 * It used to be nine `val`s on an object, referenced 119 times across five
 * files. Plain vals are not snapshot state, so making them mutable would have
 * recomposed nothing — the screens would have kept the old colours until a
 * configuration change. And three of the nine were hand-typed a digit off from
 * the values the comment above them claimed: `Void` was neither `neutral-1` nor
 * `renderer.background`, and `Ink` was two off `neutral-5`.
 *
 * These are composable getters over `LocalChrome`, so every existing call site
 * follows the theme without being rewritten, and the near-miss colours are gone
 * because the values now come from one measured place.
 *
 * New code should read `LocalChrome.current` directly — it is one lookup rather
 * than nine, and it can reach the tokens this shim has no name for
 * (`hairlineFocus`, `surface2`, the ink/mark tiers).
 */
object T {
    val Void: Color @Composable get() = LocalChrome.current.surface0
    val Plate: Color @Composable get() = LocalChrome.current.surface1
    val Line: Color @Composable get() = LocalChrome.current.hairline
    val Ink: Color @Composable get() = LocalChrome.current.textHi
    val Dim: Color @Composable get() = LocalChrome.current.textMid
    val Pick: Color @Composable get() = LocalAccent.current
    val Ok: Color @Composable get() = LocalChrome.current.okInk
    val Warn: Color @Composable get() = LocalChrome.current.warnInk
    val Bad: Color @Composable get() = LocalChrome.current.badInk
}
